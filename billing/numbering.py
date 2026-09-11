"""
Human-friendly, human-sortable document numbers: QTN-2026-0001, INV-2026-0001, RCP-2026-0001.

Sequence is per document type per calendar year, generated inside a transaction
with a row lock so concurrent requests cannot take the same number.
"""
from django.db import transaction
from django.utils import timezone

PREFIXES = {'quotation': 'QTN', 'invoice': 'INV', 'receipt': 'RCP'}


def next_document_number(model):
    prefix = PREFIXES[model._meta.model_name]
    year = timezone.localdate().year

    with transaction.atomic():
        last = (
            model.objects.select_for_update()
            .filter(number__startswith=f"{prefix}-{year}-")
            .order_by('-number')
            .values_list('number', flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.rsplit('-', 1)[1]) + 1
            except (IndexError, ValueError):
                seq = 1
        else:
            seq = 1
        return f"{prefix}-{year}-{seq:04d}"
