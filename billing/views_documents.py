"""Document lifecycle views: quotations, invoices, payments, receipts, credit notes, statements."""
import csv
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import get_template
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.audit import audit
from xhtml2pdf import pisa

from .access import staff_required, finance_required
from .emails import (
    notify_quotation_sent, notify_invoice_sent, notify_payment_confirmed,
)
from .forms import PaymentRecordForm
from .models import (
    CompanySettings, Client, Product, Quotation, Invoice, CreditNote, Payment,
    PaymentSubmission, PaymentAllocation, Receipt, TaxCategory,
)
from .numbering import next_document_number
from . import services


# ---------------------------------------------------------------- pdf helper

def _link_callback(uri, rel):
    import os
    from django.conf import settings
    media_root = str(settings.MEDIA_ROOT)
    if uri.startswith('/media/'):
        uri = uri[1:]
    if uri.startswith('media/'):
        candidate = os.path.join(media_root, uri[len('media/'):])
        if os.path.exists(candidate):
            return candidate
    return uri


def render_pdf(template_src, context):
    html = get_template(template_src).render(context)
    response = HttpResponse(content_type='application/pdf')
    status = pisa.CreatePDF(html, dest=response, link_callback=_link_callback)
    if status.err:
        return None
    return response


def _pdf(pdf, filename):
    resp = HttpResponse(pdf.getvalue(), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{filename}"'
    return resp


# ---------------------------------------------------------------- quotations

@staff_required
def quotation_list(request):
    qs = Quotation.objects.select_related('client').order_by('-issue_date', '-id')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(client__name__icontains=q))
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'billing/quotation_list.html', {
        'quotes': page.object_list, 'page_obj': page,
        'search_query': q, 'status_filter': status,
        'status_choices': Quotation.STATUS_CHOICES,
        'today': timezone.localdate(),
    })


@staff_required
def quotation_create(request):
    from .document_forms import QuotationBuilderForm
    if request.method == 'POST':
        builder = QuotationBuilderForm(request.POST)
        if builder.is_valid():
            data = builder.cleaned_data
            data['lines'] = builder.cleaned_lines()
            with transaction.atomic():
                quotation = Quotation.objects.create(
                    client=data['client'],
                    status=Quotation.DRAFT,
                    issue_date=data['issue_date'],
                    valid_until=data['valid_until'],
                    notes=data.get('notes', ''),
                    terms=data.get('terms', ''),
                    delivery_info=data.get('delivery_info', ''),
                    created_by=request.user,
                )
                quotation.number = next_document_number('quotation')
                quotation.save(update_fields=['number'])
                services.create_quotation_lines(quotation, data['lines'])
            audit('create', quotation, user=request.user)
            messages.success(request, f'Quotation {quotation.number} created as draft.')
            return redirect('quotation_detail', pk=quotation.pk)
    else:
        from .document_forms import QuotationBuilderForm
        builder = QuotationBuilderForm()
    return render(request, 'billing/quotation_form.html', {
        'builder': builder,
        'products': Product.objects.filter(is_active=True),
        'tax_categories': TaxCategory.objects.filter(is_active=True),
        'clients': Client.objects.order_by('name'),
        'today': timezone.localdate(),
        'title': 'New quotation',
    })


@staff_required
def quotation_detail(request, pk):
    quotation = get_object_or_404(Quotation.objects.select_related('client'), pk=pk)
    return render(request, 'billing/quotation_detail.html', {
        'quotation': quotation,
        'lines': quotation.lines,
        'can_convert': quotation.effective_status == Quotation.ACCEPTED and not quotation.is_converted,
        'revisions': Quotation.objects.filter(supersedes=quotation),
    })


@staff_required
@require_POST
def quotation_send(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.status == Quotation.DRAFT:
        quotation.mark_sent()
        notify_quotation_sent(quotation)
        audit('send', quotation, user=request.user)
        messages.success(request, f'Quotation {quotation.number} sent to {quotation.client.email or "client"}.')
    return redirect('quotation_detail', pk=pk)


@staff_required
@require_POST
def quotation_revise(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    new_rev = services.revise_quotation(quotation, user=request.user, note=request.POST.get('note', ''))
    audit('update', new_rev, user=request.user, detail=f'revision of {quotation.number}')
    messages.success(request, f'New revision {new_rev.number} created from {quotation.number}.')
    return redirect('quotation_detail', pk=new_rev.pk)


@finance_required
@require_POST
def quotation_convert(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    try:
        invoice, created = services.convert_quotation_to_invoice(quotation, user=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('quotation_detail', pk=pk)
    audit('convert', invoice, user=request.user, detail=f'from {quotation.number}')
    if created:
        messages.success(request, f'Invoice {invoice.number} created from {quotation.number}.')
    else:
        messages.info(request, f'Quotation was already converted (Invoice {invoice.number}).')
    return redirect('invoice_detail', pk=invoice.pk)


@staff_required
@require_POST
def quotation_delete(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.status != Quotation.DRAFT:
        messages.error(request, 'Only draft quotations can be deleted. Revoke/void via revision instead.')
        return redirect('quotation_detail', pk=pk)
    audit('void', quotation, user=request.user, detail='draft deleted')
    quotation.delete()
    messages.success(request, 'Draft quotation deleted.')
    return redirect('quotation_list')


@staff_required
def quotation_pdf(request, pk):
    quotation = get_object_or_404(Quotation.objects.select_related('client'), pk=pk)
    pdf = render_pdf('billing/pdf_quotation.html', {
        'quotation': quotation, 'lines': quotation.lines, 'company': CompanySettings.load(),
    })
    if not pdf:
        return HttpResponse('Error generating PDF', status=500)
    return _pdf(pdf, f'{quotation.number}.pdf')


# ---------------------------------------------------------------- invoices

@staff_required
def invoice_list(request):
    qs = Invoice.objects.select_related('client').order_by('-issue_date', '-id')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(client__name__icontains=q))
    if status == Invoice.OVERDUE:
        qs = [i for i in qs if i.effective_status == Invoice.OVERDUE] if not q else qs
        qs = Invoice.objects.filter(pk__in=[i.pk for i in qs])
    elif status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'billing/invoice_list.html', {
        'invoices': page.object_list, 'page_obj': page,
        'search_query': q, 'status_filter': status,
        'status_choices': Invoice.STATUS_CHOICES,
    })


@finance_required
def invoice_create(request):
    from .document_forms import InvoiceBuilderForm
    if request.method == 'POST':
        builder = InvoiceBuilderForm(request.POST)
        if builder.is_valid():
            data = builder.cleaned_data
            data['lines'] = builder.cleaned_lines()
            with transaction.atomic():
                invoice = Invoice.objects.create(
                    client=data['client'],
                    status=Invoice.DRAFT,
                    issue_date=data['issue_date'],
                    due_date=data['due_date'],
                    notes=data.get('notes', ''),
                    terms=data.get('terms', ''),
                    payment_instructions=CompanySettings.load().payment_instructions,
                    created_by=request.user,
                )
                invoice.number = next_document_number('invoice')
                invoice.save(update_fields=['number'])
                services.create_quotation_lines(invoice, data['lines'])
            audit('create', invoice, user=request.user)
            messages.success(request, f'Invoice {invoice.number} created as draft.')
            return redirect('invoice_detail', pk=invoice.pk)
    else:
        builder = InvoiceBuilderForm()
    return render(request, 'billing/invoice_form.html', {
        'builder': builder,
        'products': Product.objects.filter(is_active=True),
        'tax_categories': TaxCategory.objects.filter(is_active=True),
        'clients': Client.objects.order_by('name'),
        'today': timezone.localdate(),
        'title': 'New invoice',
    })


@staff_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related('client'), pk=pk)
    payments = Payment.objects.filter(allocations__invoice=invoice).distinct()
    allocations = PaymentAllocation.objects.filter(invoice=invoice).select_related('payment')
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'lines': invoice.lines,
        'allocations': allocations,
        'credit_notes': invoice.credit_notes.all(),
        'record_form': PaymentRecordForm(),
    })


@finance_required
@require_POST
def invoice_issue(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if invoice.status == Invoice.DRAFT:
        invoice.status = Invoice.ISSUED
        invoice.sent_at = timezone.now()
        invoice.save(update_fields=['status', 'sent_at'])
        notify_invoice_sent(invoice)
        audit('send', invoice, user=request.user)
        messages.success(request, f'Invoice {invoice.number} issued and emailed.')
    return redirect('invoice_detail', pk=pk)


@finance_required
@require_POST
def invoice_void(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if invoice.allocated_paid > 0:
        messages.error(request, 'Cannot void an invoice with payments allocated. Refund/credit first.')
        return redirect('invoice_detail', pk=pk)
    invoice.status = Invoice.VOIDED
    invoice.save(update_fields=['status'])
    audit('void', invoice, user=request.user)
    messages.success(request, f'Invoice {invoice.number} voided.')
    return redirect('invoice_detail', pk=pk)


def _vat_groups(lines):
    """Group document lines by (tax type, rate) for the invoice VAT summary."""
    groups = {}
    order = []
    for ln in lines:
        label = ln.get_tax_type_snapshot_display() if ln.tax_type_snapshot else 'Out of scope'
        key = (ln.tax_type_snapshot or 'out_of_scope', str(ln.tax_rate_snapshot))
        if key not in groups:
            groups[key] = {'label': label, 'rate': ln.tax_rate_snapshot, 'net': Decimal('0'), 'vat': Decimal('0')}
            order.append(key)
        groups[key]['net'] += ln.line_net
        groups[key]['vat'] += ln.line_vat
    return [groups[k] for k in order]


@staff_required
def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related('client'), pk=pk)
    lines = list(invoice.lines)
    pdf = render_pdf('billing/pdf_invoice.html', {
        'invoice': invoice, 'lines': lines, 'company': CompanySettings.load(),
        'vat_groups': _vat_groups(lines),
    })
    if not pdf:
        return HttpResponse('Error generating PDF', status=500)
    return _pdf(pdf, f'{invoice.number}.pdf')


@staff_required
def invoice_csv(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related('client'), pk=pk)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{invoice.number}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Description', 'Unit', 'Quantity', 'Unit price', 'Pricing mode', 'Discount %', 'Tax type', 'Tax rate %', 'Net', 'VAT', 'Total'])
    for ln in invoice.lines:
        writer.writerow([
            ln.description, ln.unit, ln.quantity, ln.unit_price, ln.get_pricing_mode_display(),
            ln.discount_percent, ln.tax_type_snapshot, ln.tax_rate_snapshot,
            ln.line_net, ln.line_vat, ln.line_total,
        ])
    writer.writerow([])
    writer.writerow(['Subtotal', '', '', '', '', '', '', '', invoice.subtotal, invoice.vat_total, invoice.total])
    return response


# ---------------------------------------------------------------- payments

@staff_required
def payment_list(request):
    payments = Payment.objects.select_related('client').order_by('-created_at')
    status = request.GET.get('status', '').strip()
    if status:
        payments = payments.filter(status=status)
    submissions = PaymentSubmission.objects.select_related('client').filter(status=Payment.PENDING)
    return render(request, 'billing/payment_list.html', {
        'payments': payments,
        'pending_submissions': submissions,
        'status_filter': status,
        'status_choices': Payment.STATUS_CHOICES,
    })


@staff_required
def payment_detail(request, pk):
    payment = get_object_or_404(Payment.objects.select_related('client'), pk=pk)
    return render(request, 'billing/payment_detail.html', {
        'payment': payment,
        'allocations': payment.allocations.select_related('invoice'),
        'open_invoices': None,
    })


@finance_required
def payment_record(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    if invoice.status == Invoice.DRAFT:
        messages.error(request, 'Issue the invoice before recording payments against it.')
        return redirect('invoice_detail', pk=invoice.pk)
    if request.method == 'POST':
        form = PaymentRecordForm(request.POST)
        if form.is_valid():
            payment, created = services.record_payment(
                client=invoice.client,
                amount=form.cleaned_data['amount'],
                method=form.cleaned_data['method'],
                transaction_ref=form.cleaned_data['transaction_ref'],
                paid_on=form.cleaned_data['paid_on'],
                notes=form.cleaned_data['notes'],
                status=Payment.PENDING,
                submitted_by=request.user,
            )
            if created:
                services.confirm_payment(payment, request.user)
                services.allocate_payment(payment, invoice, user=request.user)
                audit('payment', payment, user=request.user, detail=f'recorded against {invoice.number}')
                notify_payment_confirmed(payment, payment.receipt if hasattr(payment, "receipt") else None)
                messages.success(request, f'Payment {payment.number} recorded and confirmed.')
            else:
                messages.warning(request, f'A payment with reference {payment.transaction_ref} already exists ({payment.number}).')
            return redirect('invoice_detail', pk=invoice.pk)
    return redirect('invoice_detail', pk=invoice_pk)


@finance_required
@require_POST
def payment_verify(request, submission_pk):
    submission = get_object_or_404(PaymentSubmission, pk=submission_pk)
    approve = request.POST.get('decision') == 'approve'
    try:
        payment, receipt = services.verify_submission(
            submission, request.user, approve=approve,
            review_note=request.POST.get('review_note', ''),
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('payment_list')
    audit('verify', payment, user=request.user, detail='approved' if approve else 'rejected')
    if approve:
        messages.success(request, f'Payment {payment.number} verified. Receipt {receipt.number} issued.')
    else:
        messages.warning(request, 'Payment submission rejected.')
    return redirect('payment_list')


@finance_required
def payment_allocate(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        invoice_pk = request.POST.get('invoice')
        amount = request.POST.get('amount') or None
        invoice = get_object_or_404(Invoice, pk=invoice_pk)
        try:
            amt = services.allocate_payment(payment, invoice, amount=amount, user=request.user)
            audit('payment', payment, user=request.user, detail=f'allocated {amt} to {invoice.number}')
            messages.success(request, f'{amt} of {payment.number} allocated to {invoice.number}.')
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('payment_detail', pk=payment.pk)
    open_invoices = Invoice.objects.exclude(status__in=[Invoice.VOIDED, Invoice.PAID, Invoice.DRAFT]).filter(
        client=payment.client).order_by('due_date')
    return render(request, 'billing/payment_allocate.html', {
        'payment': payment, 'open_invoices': [i for i in open_invoices if i.balance_due > 0],
    })


@finance_required
@require_POST
def payment_deallocate(request, pk, allocation_pk):
    payment = get_object_or_404(Payment, pk=pk)
    allocation = get_object_or_404(PaymentAllocation, pk=allocation_pk, payment=payment)
    invoice = allocation.invoice
    try:
        services.deallocate_payment(payment, invoice, user=request.user)
        messages.success(request, f'Allocation to {invoice.number} removed.')
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect('payment_detail', pk=payment.pk)


@staff_required
def receipt_list(request):
    receipts = Receipt.objects.select_related('client', 'payment').order_by('-issued_at')
    paginator = Paginator(receipts, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'billing/receipt_list.html', {'receipts': page.object_list, 'page_obj': page})


@staff_required
def receipt_detail(request, pk):
    receipt = get_object_or_404(Receipt.objects.select_related('payment', 'client'), pk=pk)
    return render(request, 'billing/receipt_detail.html', {
        'receipt': receipt,
        'allocations': PaymentAllocation.objects.filter(payment=receipt.payment).select_related('invoice'),
    })


@staff_required
def receipt_pdf(request, pk):
    receipt = get_object_or_404(Receipt.objects.select_related('payment', 'client'), pk=pk)
    pdf = render_pdf('billing/pdf_receipt.html', {
        'receipt': receipt,
        'allocations': PaymentAllocation.objects.filter(payment=receipt.payment).select_related('invoice'),
        'company': CompanySettings.load(),
    })
    if not pdf:
        return HttpResponse('Error generating PDF', status=500)
    return _pdf(pdf, f'{receipt.number}.pdf')


# ---------------------------------------------------------------- credit notes

@finance_required
def credit_note_create(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    if request.method == 'POST':
        amount = request.POST.get('amount')
        reason = request.POST.get('reason', '')
        try:
            amount = Decimal(amount)
        except Exception:
            messages.error(request, 'Invalid amount.')
            return redirect('invoice_detail', pk=invoice.pk)
        if amount <= 0 or amount > invoice.balance_due:
            messages.error(request, 'Credit amount must be positive and not exceed the balance due.')
            return redirect('invoice_detail', pk=invoice.pk)
        with transaction.atomic():
            cn = CreditNote.objects.create(
                client=invoice.client, invoice=invoice, reason=reason or 'Credit adjustment',
                amount=amount, issued_by=request.user,
            )
            services.apply_credit_note(cn, user=request.user)
        audit('credit', cn, user=request.user, detail=f'against {invoice.number}')
        messages.success(request, f'Credit note {cn.number} applied to {invoice.number}.')
        return redirect('invoice_detail', pk=invoice.pk)
    return redirect('invoice_detail', pk=invoice_pk)


# ---------------------------------------------------------------- statements

@staff_required
def client_statement(request, pk):
    from .services import client_statement as build_statement
    client = get_object_or_404(Client, pk=pk)
    date_from = request.GET.get('from') or None
    date_to = request.GET.get('to') or None
    entries = build_statement(client, date_from=date_from, date_to=date_to)
    return render(request, 'billing/client_statement.html', {
        'client': client, 'entries': entries,
        'date_from': date_from, 'date_to': date_to,
        'company': CompanySettings.load(),
    })


@staff_required
def client_statement_pdf(request, pk):
    from .services import client_statement as build_statement
    client = get_object_or_404(Client, pk=pk)
    date_from = request.GET.get('from') or None
    date_to = request.GET.get('to') or None
    entries = build_statement(client, date_from=date_from, date_to=date_to)
    pdf = render_pdf('billing/pdf_statement.html', {
        'client': client, 'entries': entries, 'company': CompanySettings.load(),
        'date_from': date_from, 'date_to': date_to,
    })
    if not pdf:
        return HttpResponse('Error generating PDF', status=500)
    return _pdf(pdf, f'statement_{client.pk}.pdf')


@staff_required
def reports_export_csv(request):
    """CSV export of invoices with financial rollups."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="invoices_{timezone.localdate()}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Number', 'Client', 'Status', 'Issue date', 'Due date', 'Subtotal', 'VAT', 'Total', 'Paid', 'Balance'])
    for inv in Invoice.objects.select_related('client').order_by('issue_date'):
        writer.writerow([
            inv.number, inv.client.name, inv.get_status_display(), inv.issue_date, inv.due_date,
            inv.subtotal, inv.vat_total, inv.total, inv.amount_paid, inv.balance_due,
        ])
    return response
