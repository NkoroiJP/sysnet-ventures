"""
Document numbering, driven by CompanySettings.

Format: {PREFIX}-{YEAR}-{SEQ:04d}, per document type, allocated inside a
transaction with a row lock on the settings row so concurrent requests can
never take the same number. A rolled-back transaction may skip a number —
acceptable and expected for audit integrity.
"""
from django.db import transaction
from django.utils import timezone

DOC_FIELDS = {
    'quotation': ('quotation_prefix', 'next_quotation_seq'),
    'invoice': ('invoice_prefix', 'next_invoice_seq'),
    'receipt': ('receipt_prefix', 'next_receipt_seq'),
    'credit_note': ('credit_note_prefix', 'next_credit_note_seq'),
}


def next_document_number(doc_type) -> str:
    from .models import CompanySettings  # deferred: avoids circular import

    if doc_type == 'payment':
        return _next_payment_number()

    prefix_field, seq_field = DOC_FIELDS[doc_type]

    with transaction.atomic():
        settings_obj = CompanySettings.objects.select_for_update().get(pk=1)
        prefix = getattr(settings_obj, prefix_field)
        seq = getattr(settings_obj, seq_field)
        setattr(settings_obj, seq_field, seq + 1)
        settings_obj.save(update_fields=[seq_field])

    year = timezone.localdate().year
    return f'{prefix}-{year}-{seq:04d}'


def _next_payment_number() -> str:
    """Payments use a PAY prefix on their own sequence, allocated from the
    same locked settings row to avoid collisions."""
    from .models import CompanySettings  # deferred: avoids circular import

    with transaction.atomic():
        settings_obj = CompanySettings.objects.select_for_update().get(pk=1)
        seq = settings_obj.next_receipt_seq
        settings_obj.next_receipt_seq = seq + 1
        settings_obj.save(update_fields=['next_receipt_seq'])
        prefix = 'PAY'
    year = timezone.localdate().year
    return f'{prefix}-{year}-{seq:04d}'
