"""
Production upgrade: document numbers, tax fields, notes, validity dates,
product archiving, company currency/tax defaults, receipt references.

Existing rows are backfilled with sequential document numbers
(QTN-2026-0001, INV-2026-0001, RCP-2026-0001) based on their year and id order.
"""
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def backfill_numbers(apps, schema_editor):
    Quotation = apps.get_model('billing', 'Quotation')
    Invoice = apps.get_model('billing', 'Invoice')
    Receipt = apps.get_model('billing', 'Receipt')

    for qs, prefix, date_field in (
        (Quotation.objects.all(), 'QTN', 'date'),
        (Invoice.objects.all(), 'INV', 'date'),
        (Receipt.objects.all(), 'RCP', 'date'),
    ):
        counters = {}
        # Sort by (year, id) for stable, chronologically sensible numbers
        for obj in qs.order_by('id'):
            year = getattr(obj, date_field).year if getattr(obj, date_field) else django.utils.timezone.localdate().year
            counters[year] = counters.get(year, 0) + 1
            obj.number = f"{prefix}-{year}-{counters[year]:04d}"
            obj.save(update_fields=['number'])


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_contactmessage'),
    ]

    operations = [
        # ---- nullable number fields first (unique added after backfill) ----
        migrations.AddField('quotation', 'number', models.CharField(blank=True, max_length=20, null=True)),
        migrations.AddField('invoice', 'number', models.CharField(blank=True, max_length=20, null=True)),
        migrations.AddField('receipt', 'number', models.CharField(blank=True, max_length=20, null=True)),

        # ---- quotation ----
        migrations.AddField('quotation', 'valid_until', models.DateField(blank=True, null=True)),
        migrations.AddField('quotation', 'notes', models.TextField(blank=True, default='')),
        migrations.AddField('quotation', 'tax_rate', models.DecimalField(decimal_places=2, default=0, max_digits=5)),

        # ---- invoice ----
        migrations.AddField('invoice', 'notes', models.TextField(blank=True, default='')),
        migrations.AddField('invoice', 'tax_rate', models.DecimalField(decimal_places=2, default=0, max_digits=5)),

        # ---- receipt ----
        migrations.AddField('receipt', 'reference', models.CharField(blank=True, help_text='Transaction / cheque reference', max_length=100)),
        migrations.AddField(
            'receipt', 'created_at',
            models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),

        # ---- product ----
        migrations.AddField('product', 'is_active', models.BooleanField(default=True)),

        # ---- company profile ----
        migrations.AddField('companyprofile', 'currency', models.CharField(default='KES', help_text='Currency code shown on documents', max_length=8)),
        migrations.AddField('companyprofile', 'default_tax_rate', models.DecimalField(decimal_places=2, default=0, help_text='Default tax % applied to new documents', max_digits=5)),

        # ---- related names used by the new code ----
        migrations.AlterField('invoice', 'customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='billing.customer')),
        migrations.AlterField('quotation', 'customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quotations', to='billing.customer')),
        migrations.AlterField('receipt', 'invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='receipts', to='billing.invoice')),

        # ---- backfill then enforce uniqueness ----
        migrations.RunPython(backfill_numbers, migrations.RunPython.noop),
        migrations.AlterField('quotation', 'number', models.CharField(max_length=20, unique=True)),
        migrations.AlterField('invoice', 'number', models.CharField(max_length=20, unique=True)),
        migrations.AlterField('receipt', 'number', models.CharField(max_length=20, unique=True)),
    ]
