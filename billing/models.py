"""
Sysnet Technologies — domain models.

Layout:
- settings/company profile, tax configuration
- clients (CRM)
- catalog (products & services)
- documents: Quotation, Invoice, CreditNote with snapshotted line items
- payments: Payment (verified/confirmed), PaymentSubmission (client evidence),
  allocations of payments to invoices
- website leads: ServiceEnquiry, Project, Testimonial
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from .money import q2, multiply, vat_of, vat_component_of_gross, ZERO
from .numbering import next_document_number
from .storage import EvidencePath, validate_upload


# ==================================================================== settings

class CompanySettings(models.Model):
    """Singleton row holding company identity, defaults and numbering config."""

    # identity
    name = models.CharField(max_length=200, default='Sysnet Technologies')
    tagline = models.CharField(max_length=200, blank=True, default='ICT Solutions for Growing Businesses')
    logo = models.ImageField(upload_to='company/', blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True, default='+254710779799')
    whatsapp_number = models.CharField(max_length=32, blank=True, help_text='Digits only, international format, e.g. 254710779799')
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    physical_address = models.TextField(blank=True)
    postal_address = models.TextField(blank=True)

    # tax identity (never invent values — leave blank until provided)
    kra_pin = models.CharField(max_length=32, blank=True, verbose_name='KRA PIN')
    vat_registered = models.BooleanField(default=False)
    vat_number = models.CharField(max_length=32, blank=True, verbose_name='VAT registration number')

    currency = models.CharField(max_length=8, default='KES')

    # numbering: {prefix}-{year}-{seq} with configurable prefixes and start
    quotation_prefix = models.CharField(max_length=8, default='QTN')
    invoice_prefix = models.CharField(max_length=8, default='INV')
    receipt_prefix = models.CharField(max_length=8, default='RCP')
    credit_note_prefix = models.CharField(max_length=8, default='CN')
    next_quotation_seq = models.PositiveIntegerField(default=1)
    next_invoice_seq = models.PositiveIntegerField(default=1)
    next_receipt_seq = models.PositiveIntegerField(default=1)
    next_credit_note_seq = models.PositiveIntegerField(default=1)

    # document defaults
    quotation_validity_days = models.PositiveIntegerField(default=30)
    invoice_payment_terms_days = models.PositiveIntegerField(default=30)
    payment_instructions = models.TextField(
        blank=True,
        default='Pay via M-Pesa Paybill or bank transfer. Contact us for account details.',
    )
    document_footer = models.TextField(blank=True, default='Thank you for your business.')
    terms_and_conditions = models.TextField(blank=True)
    default_tax_category = models.ForeignKey(
        'TaxCategory', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )

    # brand
    brand_primary = models.CharField(max_length=9, default='#1d4ed8', help_text='Hex, e.g. #1d4ed8')
    brand_accent = models.CharField(max_length=9, default='#0ea5e9', help_text='Hex, e.g. #0ea5e9')

    class Meta:
        verbose_name_plural = 'Company settings'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class TaxCategory(models.Model):
    """
    Configurable, effective-dated VAT categories.

    rate_type:
      - standard: rate percent applies (e.g. 16)
      - zero: 0%, still reported as VAT-able at 0 (zero-rated)
      - exempt: 0%, reported separately from zero-rated
      - out_of_scope: no VAT treatment at all
    """
    STANDARD = 'standard'
    ZERO = 'zero'
    EXEMPT = 'exempt'
    OUT_OF_SCOPE = 'out_of_scope'
    RATE_TYPE_CHOICES = [
        (STANDARD, 'Standard rated'),
        (ZERO, 'Zero rated'),
        (EXEMPT, 'Exempt'),
        (OUT_OF_SCOPE, 'Out of scope'),
    ]

    name = models.CharField(max_length=100, unique=True)
    rate_type = models.CharField(max_length=20, choices=RATE_TYPE_CHOICES, default=STANDARD)
    rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('16.00'))
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        if self.rate_type == self.STANDARD:
            return f'{self.name} ({self.rate_percent}%)'
        return self.get_rate_type_display()

    def clean(self):
        if self.rate_type == self.STANDARD and self.rate_percent < 0:
            raise ValidationError('Standard rate cannot be negative.')
        if self.rate_type != self.STANDARD and self.rate_percent != 0:
            raise ValidationError('Only standard-rated categories may carry a non-zero rate.')

    def rate_on(self, when=None):
        """Effective percent rate on a date, or None when not effective."""
        when = when or timezone.localdate()
        if not self.is_active:
            return None
        if self.effective_from and when < self.effective_from:
            return None
        if self.effective_to and when > self.effective_to:
            return None
        return self.rate_percent

    def vat_amount(self, net: Decimal, when=None) -> Decimal:
        rate = self.rate_on(when)
        if rate is None or rate == 0:
            return ZERO
        return vat_of(net, rate)


def seed_tax_categories():
    """Create the standard Kenyan VAT categories once. Idempotent."""
    cats = [
        ('Standard rated (16%)', TaxCategory.STANDARD, Decimal('16.00'), True),
        ('Zero rated (0%)', TaxCategory.ZERO, Decimal('0.00'), False),
        ('Exempt (0%)', TaxCategory.EXEMPT, Decimal('0.00'), False),
        ('Out of scope', TaxCategory.OUT_OF_SCOPE, Decimal('0.00'), False),
    ]
    for name, rt, rate, is_default in cats:
        cat, created = TaxCategory.objects.get_or_create(
            name=name,
            defaults={'rate_type': rt, 'rate_percent': rate, 'is_default': is_default},
        )
        if created and is_default:
            settings_obj = CompanySettings.load()
            if settings_obj.default_tax_category_id is None:
                settings_obj.default_tax_category = cat
                settings_obj.save()


# ==================================================================== clients

class Client(models.Model):
    INDIVIDUAL = 'individual'
    BUSINESS = 'business'
    CLIENT_TYPE_CHOICES = [(INDIVIDUAL, 'Individual'), (BUSINESS, 'Business')]

    ACTIVE = 'active'
    PROSPECT = 'prospect'
    INACTIVE = 'inactive'
    STATUS_CHOICES = [(ACTIVE, 'Active'), (PROSPECT, 'Prospect'), (INACTIVE, 'Inactive')]

    client_type = models.CharField(max_length=12, choices=CLIENT_TYPE_CHOICES, default=BUSINESS)
    name = models.CharField(max_length=255, help_text='Company name, or full name for individuals')
    contact_person = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    billing_address = models.TextField(blank=True)
    delivery_address = models.TextField(blank=True)
    kra_pin = models.CharField(max_length=32, blank=True, verbose_name='KRA PIN')
    vat_details = models.CharField(max_length=64, blank=True, help_text='VAT registration number if applicable')
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PROSPECT)
    created_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='created_clients')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    # ---- financial rollups -------------------------------------------
    @property
    def total_invoiced(self) -> Decimal:
        return q2(sum((inv.total for inv in self.invoices.exclude(status=Invoice.VOIDED)), ZERO))

    @property
    def total_paid(self) -> Decimal:
        return q2(sum((p.amount for p in self.verified_payments()), ZERO))

    def verified_payments(self):
        return Payment.objects.filter(status=Payment.CONFIRMED, allocations__invoice__client=self).distinct()

    @property
    def outstanding(self) -> Decimal:
        return q2(sum((inv.balance_due for inv in self.invoices.exclude(status__in=[Invoice.VOIDED, Invoice.DRAFT])), ZERO))

    @property
    def overdue_amount(self) -> Decimal:
        today = timezone.localdate()
        overdue = [inv for inv in self.invoices.exclude(status__in=[Invoice.VOIDED, Invoice.DRAFT, Invoice.PAID])
                   if inv.due_date and inv.due_date < today]
        return q2(sum((inv.balance_due for inv in overdue), ZERO))


class ClientContact(models.Model):
    """Additional contacts under a business client."""
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.name} ({self.client.name})'


# ==================================================================== catalog

class Product(models.Model):
    SERVICE = 'service'
    PRODUCT = 'product'
    TYPE_CHOICES = [(SERVICE, 'Service'), (PRODUCT, 'Product')]

    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64, blank=True, help_text='SKU or service code')
    category = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=24, blank=True, help_text='e.g. item, hour, month, licence')
    selling_price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    tax_category = models.ForeignKey(TaxCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name='products')
    is_active = models.BooleanField(default=True)
    track_stock = models.BooleanField(default=False)
    stock_quantity = models.IntegerField(default=0)
    public_show = models.BooleanField(default=False, help_text='Show on the public website catalogue')
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        if self.stock_quantity < 0:
            raise ValidationError('Stock quantity cannot be negative.')


# ==================================================================== documents

def _validate_money(value):
    if value is None or value < 0:
        raise ValidationError('Amounts cannot be negative.')


class DocumentLine(models.Model):
    """
    Snapshot line shared by quotations, invoices and credit notes.

    Historical documents keep their own description, price and tax values even
    after catalog changes. `pricing_mode` records whether the entered unit
    price was VAT-exclusive or VAT-inclusive at creation time.
    """
    PRICING_EXCLUSIVE = 'exclusive'
    PRICING_INCLUSIVE = 'inclusive'
    PRICING_CHOICES = [(PRICING_EXCLUSIVE, 'VAT exclusive'), (PRICING_INCLUSIVE, 'VAT inclusive')]

    content_type = models.ForeignKey(ContentType, null=True, editable=False, on_delete=models.SET_NULL, related_name='+')
    object_id = models.PositiveBigIntegerField(null=True, editable=False, db_index=True)
    parent_object = GenericForeignKey('content_type', 'object_id')

    catalog_item = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    description = models.CharField(max_length=512)
    unit = models.CharField(max_length=24, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, validators=[_validate_money])
    pricing_mode = models.CharField(max_length=12, choices=PRICING_CHOICES, default=PRICING_EXCLUSIVE)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO, validators=[MinValueValidator(Decimal('0'))])
    tax_category = models.ForeignKey(TaxCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    tax_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    tax_type_snapshot = models.CharField(max_length=20, choices=TaxCategory.RATE_TYPE_CHOICES, blank=True, default=TaxCategory.OUT_OF_SCOPE)
    line_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['line_order', 'id']

    # ---- computed -----------------------------------------------------
    @property
    def gross_unit_price(self) -> Decimal:
        """Unit price as entered (exclusive or inclusive per pricing_mode)."""
        return q2(self.unit_price)

    @property
    def line_gross(self) -> Decimal:
        """Quantity × entered unit price, before discount (the 'entered' value)."""
        return multiply(self.quantity, self.unit_price)

    @property
    def discount_amount(self) -> Decimal:
        return q2(self.line_gross * self.discount_percent / Decimal('100'))

    @property
    def line_net(self) -> Decimal:
        """Net (VAT-exclusive) amount after discount."""
        if self.pricing_mode == self.PRICING_INCLUSIVE:
            rate = self.tax_rate_snapshot
            after_discount = self.line_gross - self.discount_amount
            if rate and rate > 0:
                return q2(after_discount / (Decimal('1') + Decimal(rate) / Decimal('100')))
            return q2(after_discount)
        return q2(self.line_gross - self.discount_amount)

    @property
    def line_vat(self) -> Decimal:
        if self.pricing_mode == self.PRICING_INCLUSIVE:
            return q2(self.line_net_after_discount_and_gross_total()[1])
        rate = self.tax_rate_snapshot
        if rate and rate > 0:
            return vat_of(self.line_net, rate)
        return ZERO

    def line_net_after_discount_and_gross_total(self):
        """For inclusive lines: (net, vat) extracted from the discounted gross."""
        rate = self.tax_rate_snapshot
        after_discount = q2(self.line_gross - self.discount_amount)
        if self.pricing_mode == self.PRICING_INCLUSIVE and rate and rate > 0:
            vat = vat_component_of_gross(after_discount, rate)
            return q2(after_discount - vat), vat
        return after_discount, ZERO

    @property
    def line_total(self) -> Decimal:
        """Gross total for the line (net + VAT), i.e. what the client pays.
        For inclusive lines this preserves the (discounted) entered gross;
        for exclusive lines VAT is added on top of the net."""
        if self.pricing_mode == self.PRICING_INCLUSIVE:
            net, vat = self.line_net_after_discount_and_gross_total()
            return q2(net + vat)
        return q2(self.line_net + self.line_vat)

    def snapshot_tax(self, when=None):
        """Copy the linked tax category's rate/type onto the line."""
        if self.tax_category_id:
            rate = self.tax_category.rate_on(when)
            if rate is None:
                rate = self.tax_category.rate_percent
            self.tax_rate_snapshot = rate
            self.tax_type_snapshot = self.tax_category.rate_type
        else:
            self.tax_rate_snapshot = ZERO
            self.tax_type_snapshot = TaxCategory.OUT_OF_SCOPE


class Quotation(models.Model):
    DRAFT = 'draft'
    SENT = 'sent'
    VIEWED = 'viewed'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'
    EXPIRED = 'expired'
    CONVERTED = 'converted'
    STATUS_CHOICES = [
        (DRAFT, 'Draft'), (SENT, 'Sent'), (VIEWED, 'Viewed'),
        (ACCEPTED, 'Accepted'), (REJECTED, 'Rejected'), (EXPIRED, 'Expired'),
        (CONVERTED, 'Converted'),
    ]

    number = models.CharField(max_length=32, unique=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='quotations')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=DRAFT)
    issue_date = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    delivery_info = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='revised_by')
    created_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='quotations_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # email / tracking
    sent_at = models.DateTimeField(null=True, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)

    class Meta:
        ordering = ['-issue_date', '-id']

    def __str__(self):
        return f'{self.number} — {self.client.name}'

    # ---- totals (server-side, always recomputed) -----------------------
    @property
    def lines(self):
        return DocumentLine.objects.filter(
            content_type=ContentType_of(self), object_id=self.pk
        ).select_related('tax_category')

    def lines_qs(self):
        return self.lines

    @property
    def subtotal(self) -> Decimal:
        """Net (VAT-exclusive) subtotal after discounts."""
        return q2(sum((ln.line_net for ln in self.lines), ZERO))

    @property
    def discount_total(self) -> Decimal:
        return q2(sum((ln.discount_amount for ln in self.lines), ZERO))

    @property
    def vat_total(self) -> Decimal:
        return q2(sum((ln.line_vat for ln in self.lines), ZERO))

    @property
    def total(self) -> Decimal:
        return q2(self.subtotal + self.vat_total)

    @property
    def is_expired(self):
        return bool(self.valid_until and self.valid_until < timezone.localdate()
                    and self.status in (self.SENT, self.VIEWED))

    @property
    def effective_status(self):
        if self.status == self.SENT and self.is_expired:
            return self.EXPIRED
        return self.status

    @property
    def is_converted(self):
        return hasattr(self, 'invoice')

    # ---- lifecycle -----------------------------------------------------
    def mark_sent(self):
        self.status = self.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at'])

    def mark_viewed(self):
        if self.status == self.SENT and not self.viewed_at:
            self.status = self.VIEWED
            self.viewed_at = timezone.now()
            self.save(update_fields=['status', 'viewed_at'])


class Invoice(models.Model):
    DRAFT = 'draft'
    ISSUED = 'issued'
    PARTIALLY_PAID = 'partially_paid'
    PAID = 'paid'
    OVERDUE = 'overdue'
    VOIDED = 'voided'
    CREDITED = 'credited'
    STATUS_CHOICES = [
        (DRAFT, 'Draft'), (ISSUED, 'Issued'), (PARTIALLY_PAID, 'Partially paid'),
        (PAID, 'Paid'), (OVERDUE, 'Overdue'), (VOIDED, 'Voided'), (CREDITED, 'Credited'),
    ]

    number = models.CharField(max_length=32, unique=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='invoices')
    quotation = models.OneToOneField(Quotation, null=True, blank=True, on_delete=models.SET_NULL, related_name='invoice')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT)
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    payment_instructions = models.TextField(blank=True)
    created_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='invoices_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-issue_date', '-id']

    def __str__(self):
        return f'{self.number} — {self.client.name}'

    @property
    def lines(self):
        return DocumentLine.objects.filter(
            content_type=ContentType_of(self), object_id=self.pk
        ).select_related('tax_category')

    def lines_qs(self):
        return self.lines

    @property
    def subtotal(self) -> Decimal:
        return q2(sum((ln.line_net for ln in self.lines), ZERO))

    @property
    def discount_total(self) -> Decimal:
        return q2(sum((ln.discount_amount for ln in self.lines), ZERO))

    @property
    def vat_total(self) -> Decimal:
        return q2(sum((ln.line_vat for ln in self.lines), ZERO))

    @property
    def total(self) -> Decimal:
        return q2(self.subtotal + self.vat_total)

    @property
    def allocated_paid(self) -> Decimal:
        if self.pk is None:
            return ZERO
        agg = self.allocations.aggregate(t=models.Sum('amount'))
        return q2(agg['t'] or 0)

    @property
    def amount_paid(self) -> Decimal:
        return self.allocated_paid

    @property
    def balance_due(self) -> Decimal:
        return q2(self.total - self.allocated_paid)

    @property
    def is_overdue(self):
        return (self.due_date and self.due_date < timezone.localdate()
                and self.status not in (self.PAID, self.VOIDED, self.CREDITED, self.DRAFT))

    @property
    def effective_status(self):
        if self.status in (self.DRAFT, self.VOIDED, self.CREDITED, self.PAID):
            return self.status
        if self.is_overdue:
            return self.OVERDUE
        if self.allocated_paid > 0:
            return self.PARTIALLY_PAID if self.balance_due > 0 else self.PAID
        return self.status

    def sync_status_from_payments(self):
        """Recompute issued/partially paid/paid from allocations. Called after payment changes."""
        if self.status in (self.DRAFT, self.VOIDED, self.CREDITED):
            return
        if self.balance_due <= 0 and self.total > 0:
            self.status = self.PAID
        elif self.allocated_paid > 0:
            self.status = self.PARTIALLY_PAID
        elif self.status in (self.PARTIALLY_PAID, self.PAID):
            self.status = self.ISSUED
        self.save(update_fields=['status'])

    def refresh_overdue(self):
        if self.status == self.ISSUED and self.is_overdue:
            self.status = self.OVERDUE
            self.save(update_fields=['status'])

    @classmethod
    def refresh_overdue_statuses(cls):
        return cls.objects.filter(
            status=cls.ISSUED, due_date__lt=timezone.localdate(),
        ).update(status=cls.OVERDUE)

    @property
    def payment_progress(self):
        if self.total <= 0:
            return 0
        return min(100, int(round(self.allocated_paid / self.total * 100)))


class CreditNote(models.Model):
    number = models.CharField(max_length=32, unique=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='credit_notes')
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name='credit_notes')
    reason = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[_validate_money])
    applied_to_invoice = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    issued_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='credit_notes_issued')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.number} — {self.client.name}'

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_document_number('credit_note')
        super().save(*args, **kwargs)

    def apply(self, user=None):
        """Apply this credit note against its invoice (reduces balance)."""
        from .services import apply_credit_note
        apply_credit_note(self, user=user)


class Payment(models.Model):
    """Money actually received (or recorded) by the company.

    Lifecycle: pending -> verified (staff confirms) -> confirmed (receipts may
    reference it). Client-submitted payment references stay pending until
    verified. Only confirmed payments may be allocated and receipted.
    """
    PENDING = 'pending'
    VERIFIED = 'verified'
    CONFIRMED = 'confirmed'
    REJECTED = 'rejected'
    STATUS_CHOICES = [
        (PENDING, 'Pending verification'), (VERIFIED, 'Verified'),
        (CONFIRMED, 'Confirmed'), (REJECTED, 'Rejected'),
    ]

    METHOD_CHOICES = [
        ('mpesa', 'M-Pesa'),
        ('bank', 'Bank transfer'),
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('cheque', 'Cheque'),
        ('other', 'Other'),
    ]

    number = models.CharField(max_length=32, unique=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[_validate_money])
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='mpesa')
    transaction_ref = models.CharField(max_length=100, blank=True, help_text='M-Pesa code / bank ref / cheque no.')
    paid_on = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    submitted_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='payments_submitted')
    verified_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='payments_verified')
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paid_on', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['method', 'transaction_ref'],
                condition=~models.Q(transaction_ref=''),
                name='uniq_payment_method_ref',
            )
        ]

    def __str__(self):
        return f'{self.number} — {self.amount} ({self.get_method_display()})'

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_document_number('payment')
        super().save(*args, **kwargs)

    @property
    def allocated_total(self) -> Decimal:
        agg = self.allocations.aggregate(t=models.Sum('amount'))
        return q2(agg['t'] or 0)

    @property
    def unallocated(self) -> Decimal:
        return q2(self.amount - self.allocated_total)

    def allocate_to(self, invoice, user=None):
        from .services import allocate_payment
        allocate_payment(self, invoice, user=user)


class PaymentSubmission(models.Model):
    """Client-submitted payment reference + optional proof of payment.

    Creating this does NOT mark anything paid. Staff must verify, which
    creates/updates the underlying Payment to `verified` and allows allocation.
    """
    payment = models.OneToOneField(Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name='submission')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='payment_submissions')
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[_validate_money])
    method = models.CharField(max_length=20, choices=Payment.METHOD_CHOICES, default='mpesa')
    transaction_ref = models.CharField(max_length=100, blank=True)
    paid_on = models.DateField(default=timezone.localdate)
    note = models.TextField(blank=True)
    evidence = models.FileField(upload_to=EvidencePath(), null=True, blank=True, validators=[validate_upload])
    status = models.CharField(max_length=12, choices=Payment.STATUS_CHOICES, default=Payment.PENDING)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='submissions_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Submission {self.pk} — {self.client.name} — {self.amount}'

    def promote_to_payment(self, user=None):
        """Create (or reuse) the linked Payment in pending->verified state."""
        from .services import promote_submission
        return promote_submission(self, user=user)


class PaymentAllocation(models.Model):
    """Allocates a confirmed/verified payment against a specific invoice."""
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='allocations')
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='allocations')
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[_validate_money])
    allocated_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['payment', 'invoice'], name='uniq_payment_invoice_allocation'),
        ]

    def __str__(self):
        return f'{self.payment.number} → {self.invoice.number}: {self.amount}'


class Receipt(models.Model):
    """Issued only against a confirmed payment (and its allocations)."""
    number = models.CharField(max_length=32, unique=True)
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name='receipt')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='receipts')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    issued_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='receipts_issued')
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f'{self.number} — {self.payment.number}'

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_document_number('receipt')
        super().save(*args, **kwargs)


class NotificationLog(models.Model):
    """Tracks every outbound notification (email) and its delivery status."""

    PENDING = 'pending'
    SENT = 'sent'
    FAILED = 'failed'
    STATUS_CHOICES = [(PENDING, 'Pending'), (SENT, 'Sent'), (FAILED, 'Failed')]

    purpose = models.CharField(max_length=64)
    recipient = models.CharField(max_length=500)
    subject = models.CharField(max_length=300)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    attempts = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.purpose} → {self.recipient} ({self.status})'


# ==================================================================== website

class ServicePage(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=400, blank=True)
    icon = models.CharField(max_length=60, blank=True, help_text='Font Awesome class, e.g. fa-network-wired')
    description = models.TextField(blank=True, help_text='Rich overview paragraph(s)')
    problems = models.JSONField(default=list, blank=True, help_text='Business problems addressed')
    deliverables = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'title']

    def __str__(self):
        return self.title


class ServiceEnquiry(models.Model):
    """Public 'Request a Quote' / service-page enquiries. Does NOT auto-create invoices."""
    STATUS_CHOICES = [('new', 'New'), ('in_review', 'In review'), ('quoted', 'Quoted'), ('closed', 'Closed')]

    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=32, blank=True)
    company = models.CharField(max_length=200, blank=True)
    services = models.JSONField(default=list, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} — {self.get_status_display()}'


class ContactMessage(models.Model):
    CATEGORY_CHOICES = [
        ('general', 'General'), ('sales', 'Sales'), ('support', 'Support'),
        ('billing', 'Billing'), ('careers', 'Careers'),
    ]

    name = models.CharField(max_length=200)  # sender name
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general')
    email = models.EmailField()
    phone = models.CharField(max_length=32, blank=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.get_category_display()})'


class Project(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    category = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    technologies = models.JSONField(default=list, blank=True)
    image = models.ImageField(upload_to='projects/', blank=True, null=True)
    client_name = models.CharField(max_length=200, blank=True, help_text='Shown only if provided')
    is_public = models.BooleanField(default=False, help_text='Approved for public display')
    completed_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-completed_on', '-created_at']

    def __str__(self):
        return self.title


class Testimonial(models.Model):
    client_name = models.CharField(max_length=200)
    client_role = models.CharField(max_length=200, blank=True)
    quote = models.TextField()
    is_public = models.BooleanField(default=False, help_text='Only real, approved testimonials are shown')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.client_name}'


# ---------------------------------------------------------------- helpers

def ContentType_of(instance):
    """ContentType for an instance's model, cached by Django."""
    from django.contrib.contenttypes.models import ContentType
    return ContentType.objects.get_for_model(type(instance))
