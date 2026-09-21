"""
Business-logic service layer. Views stay thin; all financial mutations run
inside transactions here, are audited, and enforce the accounting rules:

- Totals always computed server-side from snapshotted lines.
- Issued documents are never edited or deleted — void/credit instead.
- Payments must be verified/confirmed before allocation and receipts.
- Allocations cannot exceed the invoice balance or the payment remainder.
- Idempotency guards prevent duplicate conversions, receipts, allocations.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.audit import audit

from .models import (
    CompanySettings, Client, TaxCategory, DocumentLine,
    Quotation, Invoice, CreditNote, Payment, PaymentSubmission,
    PaymentAllocation, Receipt,
)
from .money import q2, ZERO
from .numbering import next_document_number
from .storage import validate_upload


def _chain_q(base_number: str) -> Q:
    """Match a quotation or any revision whose supersede chain includes it."""
    return (
        Q(number=base_number)
        | Q(supersedes__number=base_number)
        | Q(supersedes__supersedes__number=base_number)
        | Q(supersedes__supersedes__supersedes__number=base_number)
        | Q(supersedes__supersedes__supersedes__supersedes__number=base_number)
    )


# ---------------------------------------------------------------- quotation

def create_quotation_lines(parent, lines_data, when=None):
    """lines_data: list of dicts with description, quantity, unit_price,
    pricing_mode, discount_percent, tax_category (obj/id/None), catalog_item
    (obj/id/None), unit. Snapshots tax rate + type at creation."""
    when = when or timezone.localdate()
    for data in lines_data:
        tax_cat = data.get('tax_category')
        if isinstance(tax_cat, int):
            tax_cat = TaxCategory.objects.filter(pk=tax_cat).first()
        item = data.get('catalog_item')
        line = DocumentLine(
            description=data['description'],
            unit=data.get('unit', ''),
            quantity=q2(data['quantity']),
            unit_price=q2(data['unit_price']),
            pricing_mode=data.get('pricing_mode', DocumentLine.PRICING_EXCLUSIVE),
            discount_percent=q2(data.get('discount_percent') or 0),
            tax_category=tax_cat,
            catalog_item_id=item.pk if hasattr(item, 'pk') else item,
            line_order=data.get('line_order', 0),
        )
        line.snapshot_tax(when)
        line.parent_object = parent
        line.save()


def _copy_lines(source_lines, parent):
    for ln in source_lines:
        DocumentLine.objects.create(
            parent_object=parent, description=ln.description, unit=ln.unit,
            quantity=ln.quantity, unit_price=ln.unit_price, pricing_mode=ln.pricing_mode,
            discount_percent=ln.discount_percent, tax_category_id=ln.tax_category_id,
            tax_rate_snapshot=ln.tax_rate_snapshot, tax_type_snapshot=ln.tax_type_snapshot,
            catalog_item_id=ln.catalog_item_id, line_order=ln.line_order,
        )


def revise_quotation(quotation: Quotation, user=None, note=''):
    """Create the next revision as a fresh draft; the original is preserved."""
    with transaction.atomic():
        old_lines = list(quotation.lines)
        old_pk = quotation.pk
        old_number = quotation.number
        base = old_number.rsplit('-', 1)[0] if '-' in old_number else old_number

        quotation.pk = None  # clone onto a new row
        quotation.number = next_document_number('quotation')
        quotation.status = Quotation.DRAFT
        quotation.revision = Quotation.objects.filter(
            Q(pk=old_pk) | Q(supersedes_id=old_pk)
        ).count() + 1
        quotation.supersedes_id = old_pk
        quotation.sent_at = quotation.viewed_at = quotation.decided_at = None
        quotation.decision_note = note
        quotation.created_by = user
        quotation.save()

        _copy_lines(old_lines, quotation)
    return quotation


def convert_quotation_to_invoice(quotation: Quotation, user=None):
    """Snapshot-copy an accepted quotation into a new invoice. Idempotent."""
    if quotation.is_converted:
        return quotation.invoice, False
    if quotation.effective_status != Quotation.ACCEPTED:
        raise ValueError('Only accepted quotations can be converted.')

    with transaction.atomic():
        invoice = Invoice.objects.create(
            client=quotation.client,
            quotation=quotation,
            issue_date=timezone.localdate(),
            due_date=timezone.localdate() + timezone.timedelta(
                days=CompanySettings.load().invoice_payment_terms_days),
            notes=quotation.notes,
            terms=quotation.terms,
            payment_instructions=CompanySettings.load().payment_instructions,
            created_by=user,
        )
        invoice.number = next_document_number('invoice')
        invoice.save(update_fields=['number'])

        _copy_lines(quotation.lines, invoice)

        quotation.status = Quotation.CONVERTED
        quotation.save(update_fields=['status'])
    return invoice, True


# ---------------------------------------------------------------- payments

def record_payment(*, client, amount, method, transaction_ref='', paid_on=None,
                   notes='', status=Payment.PENDING, submitted_by=None):
    """Create a payment (staff-recorded or client-submitted).
    Idempotent on (method, transaction_ref) via the DB constraint + lookup."""
    amount = q2(amount)
    if amount <= 0:
        raise ValueError('Payment amount must be positive.')
    if transaction_ref:
        existing = Payment.objects.filter(method=method, transaction_ref=transaction_ref).first()
        if existing:
            return existing, False

    payment = Payment.objects.create(
        client=client, amount=amount, method=method,
        transaction_ref=transaction_ref, paid_on=paid_on or timezone.localdate(),
        notes=notes, status=status, submitted_by=submitted_by,
    )
    return payment, True


def promote_submission(submission: PaymentSubmission):
    """Turn a client submission into a Payment in PENDING state (not paid yet)."""
    if submission.payment_id:
        return submission.payment
    payment, created = record_payment(
        client=submission.client, amount=submission.amount, method=submission.method,
        transaction_ref=submission.transaction_ref, paid_on=submission.paid_on,
        notes=submission.note, status=Payment.PENDING, submitted_by=None,
    )
    PaymentSubmission.objects.filter(pk=submission.pk).update(payment=payment)
    submission.refresh_from_db()
    return payment


def verify_submission(submission: PaymentSubmission, user, approve=True, review_note=''):
    """Staff verification of a client submission.
    Approve -> payment CONFIRMED + receipt issued. Reject -> payment REJECTED.
    The invoice is never auto-marked paid by submission alone."""
    if submission.status in (Payment.CONFIRMED, Payment.REJECTED):
        raise ValueError('Submission already reviewed.')

    with transaction.atomic():
        payment = promote_submission(submission)
        now = timezone.now()

        payment.status = Payment.CONFIRMED if approve else Payment.REJECTED
        payment.verified_by = user
        payment.verified_at = now
        payment.save(update_fields=['status', 'verified_by', 'verified_at'])

        submission.status = payment.status
        submission.review_note = review_note
        submission.reviewed_by = user
        submission.reviewed_at = now
        submission.save(update_fields=['status', 'review_note', 'reviewed_by', 'reviewed_at'])

        receipt = issue_receipt_for_payment(payment, user) if approve else None
        audit('verify', payment, user=user, detail='approved' if approve else 'rejected')
        return payment, receipt


def confirm_payment(payment: Payment, user):
    """Staff directly confirming a recorded payment. Receipt issued on confirm.
    Email notification failures never break the financial transaction."""
    if payment.status == Payment.CONFIRMED:
        receipt = issue_receipt_for_payment(payment, user)
        return payment, receipt
    with transaction.atomic():
        payment.status = Payment.CONFIRMED
        payment.verified_by = user
        payment.verified_at = timezone.now()
        payment.save(update_fields=['status', 'verified_by', 'verified_at'])
        receipt = issue_receipt_for_payment(payment, user)
    try:
        from .emails import notify_payment_confirmed
        notify_payment_confirmed(payment, receipt)
    except Exception:
        pass  # already logged in NotificationLog by the email layer
    return payment, receipt


def allocate_payment(payment: Payment, invoice: Invoice, amount=None, user=None):
    """Allocate part or all of a payment's unallocated remainder to an invoice."""
    if payment.status not in (Payment.VERIFIED, Payment.CONFIRMED):
        raise ValueError('Only verified/confirmed payments can be allocated.')

    remainder = payment.unallocated
    amt = q2(amount) if amount is not None else min(remainder, invoice.balance_due)
    if amt <= 0:
        raise ValueError('Allocation amount must be positive.')
    if amt > remainder:
        raise ValueError('Allocation exceeds the unallocated payment remainder.')
    if amt > invoice.balance_due:
        raise ValueError('Allocation exceeds the invoice balance due.')
    if PaymentAllocation.objects.filter(payment=payment, invoice=invoice).exists():
        raise ValueError('This payment is already allocated to this invoice.')

    with transaction.atomic():
        PaymentAllocation.objects.create(payment=payment, invoice=invoice, amount=amt, allocated_by=user)
        invoice.sync_status_from_payments()
    return amt


def deallocate_payment(payment: Payment, invoice: Invoice, user=None):
    """Remove an allocation (correction flow) and resync the invoice."""
    with transaction.atomic():
        alloc = PaymentAllocation.objects.filter(payment=payment, invoice=invoice).first()
        if not alloc:
            raise ValueError('No allocation to remove.')
        alloc.delete()
        invoice.sync_status_from_payments()


def issue_receipt_for_payment(payment: Payment, user) -> Receipt:
    """Issue the receipt for a confirmed payment. Idempotent."""
    if payment.status != Payment.CONFIRMED:
        raise ValueError('Receipts are only issued for confirmed payments.')
    if hasattr(payment, 'receipt'):
        return payment.receipt
    return Receipt.objects.create(
        payment=payment, client=payment.client, amount=payment.amount, issued_by=user,
    )


def apply_credit_note(credit_note: CreditNote, user=None):
    """Apply a credit note against its invoice, reducing the effective balance."""
    if credit_note.applied_to_invoice:
        return credit_note
    if not credit_note.invoice:
        raise ValueError('Credit note has no invoice to apply against.')
    with transaction.atomic():
        credit_note.applied_to_invoice = True
        credit_note.save(update_fields=['applied_to_invoice'])
        credit_note.invoice.sync_status_from_payments()
    return credit_note


def client_statement(client: Client, date_from=None, date_to=None):
    """Line-by-line account statement entries (chronological, with balances)."""
    invoices = client.invoices.exclude(status=Invoice.VOIDED)
    if date_from:
        invoices = invoices.filter(issue_date__gte=date_from)
    if date_to:
        invoices = invoices.filter(issue_date__lte=date_to)

    entries = []
    for inv in invoices.order_by('issue_date', 'id'):
        entries.append({
            'date': inv.issue_date, 'type': 'Invoice', 'ref': inv.number,
            'description': f'Invoice {inv.number}',
            'debit': inv.total, 'credit': ZERO, 'balance': ZERO,
        })

    receipts = Receipt.objects.filter(client=client).select_related('payment')
    if date_from:
        receipts = receipts.filter(payment__paid_on__gte=date_from)
    if date_to:
        receipts = receipts.filter(payment__paid_on__lte=date_to)
    for r in receipts.order_by('payment__paid_on', 'id'):
        entries.append({
            'date': r.payment.paid_on, 'type': 'Receipt', 'ref': r.number,
            'description': f'Payment {r.payment.number} ({r.payment.get_method_display()})',
            'debit': ZERO, 'credit': r.amount, 'balance': ZERO,
        })

    for cn in client.credit_notes.filter(applied_to_invoice=True).order_by('created_at'):
        entries.append({
            'date': cn.created_at.date(), 'type': 'Credit note', 'ref': cn.number,
            'description': cn.reason, 'debit': ZERO, 'credit': cn.amount, 'balance': ZERO,
        })

    entries.sort(key=lambda e: (e['date'], str(e['ref'])))
    running = ZERO
    for e in entries:
        running = q2(running + e['debit'] - e['credit'])
        e['balance'] = running
    return entries
