from decimal import Decimal, ROUND_HALF_UP

from django.db import models, transaction
from django.utils import timezone
from django.db.models import Sum, F, Q

from .numbering import next_document_number


def q2(value):
    """Quantize a Decimal to 2 places (half-up) for money math."""
    if value is None:
        return Decimal('0.00')
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class Customer(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def total_billed(self):
        return q2(self.invoices.aggregate(t=Sum(F('items__quantity') * F('items__unit_price')))['t'])

    @property
    def total_outstanding(self):
        return self.invoices.exclude(status=Invoice.PAID).aggregate(
            t=Sum(F('items__quantity') * F('items__unit_price'))
        )['t'] or Decimal('0.00')


class Product(models.Model):
    SERVICE = 'service'
    PRODUCT = 'product'
    TYPE_CHOICES = [
        (SERVICE, 'Service'),
        (PRODUCT, 'Product'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    product_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=SERVICE)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Quotation(models.Model):
    DRAFT = 'draft'
    SENT = 'sent'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'

    STATUS_CHOICES = [
        (DRAFT, 'Draft'),
        (SENT, 'Sent'),
        (ACCEPTED, 'Accepted'),
        (REJECTED, 'Rejected'),
    ]

    number = models.CharField(max_length=20, unique=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='quotations')
    date = models.DateField(default=timezone.now)
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    notes = models.TextField(blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_document_number(Quotation)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.number} - {self.customer.name}"

    @property
    def subtotal(self):
        return q2(self.items.aggregate(total=Sum(F('quantity') * F('unit_price')))['total'])

    @property
    def tax_amount(self):
        return q2(self.subtotal * self.tax_rate / Decimal('100'))

    @property
    def total_amount(self):
        return q2(self.subtotal + self.tax_amount)

    @property
    def is_converted(self):
        return hasattr(self, 'invoice')


class QuotationItem(models.Model):
    quotation = models.ForeignKey(Quotation, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=255)  # Snapshot of product name or custom desc
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['id']

    @property
    def total_price(self):
        return q2(self.quantity * self.unit_price)


class Invoice(models.Model):
    PENDING = 'pending'
    PAID = 'paid'
    OVERDUE = 'overdue'

    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PAID, 'Paid'),
        (OVERDUE, 'Overdue'),
    ]

    number = models.CharField(max_length=20, unique=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    quotation = models.OneToOneField(Quotation, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice')
    date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    notes = models.TextField(blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_document_number(Invoice)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.number} - {self.customer.name}"

    # ---- Money ----
    @property
    def subtotal(self):
        return q2(self.items.aggregate(total=Sum(F('quantity') * F('unit_price')))['total'])

    @property
    def tax_amount(self):
        return q2(self.subtotal * self.tax_rate / Decimal('100'))

    @property
    def total_amount(self):
        return q2(self.subtotal + self.tax_amount)

    @property
    def amount_paid(self):
        return q2(self.receipts.aggregate(total=Sum('amount'))['total'])

    @property
    def balance_due(self):
        return q2(self.total_amount - self.amount_paid)

    # ---- Status management ----
    @property
    def is_overdue(self):
        return self.status != self.PAID and self.due_date is not None and self.due_date < timezone.localdate()

    @property
    def effective_status(self):
        """Display status: auto-flags overdue without requiring a cron job."""
        if self.status == self.PAID:
            return self.PAID
        if self.is_overdue:
            return self.OVERDUE
        return self.status

    @property
    def payment_progress(self):
        if self.total_amount <= 0:
            return 0
        return min(100, int(round(self.amount_paid / self.total_amount * 100)))

    def mark_paid_if_settled(self):
        if self.status != self.PAID and self.balance_due <= 0:
            self.status = self.PAID
            self.save(update_fields=['status'])
            return True
        return False

    @classmethod
    def refresh_overdue_statuses(cls):
        """Promote pending invoices past their due date to overdue. Run daily."""
        return cls.objects.filter(status=cls.PENDING, due_date__lt=timezone.localdate()).update(status=cls.OVERDUE)


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['id']

    @property
    def total_price(self):
        return q2(self.quantity * self.unit_price)


class Receipt(models.Model):
    PAYMENT_METHODS = [
        ('Cash', 'Cash'),
        ('Bank Transfer', 'Bank Transfer'),
        ('M-Pesa', 'M-Pesa'),
        ('Cheque', 'Cheque'),
        ('Card', 'Card'),
        ('Other', 'Other'),
    ]

    number = models.CharField(max_length=20, unique=True, blank=True)
    invoice = models.ForeignKey(Invoice, related_name='receipts', on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50, blank=True, choices=PAYMENT_METHODS)
    reference = models.CharField(max_length=100, blank=True, help_text="Transaction / cheque reference")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_document_number(Receipt)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.number} for {self.invoice.number}"

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        with transaction.atomic():
            if invoice.status == Invoice.PAID and invoice.balance_due > 0:
                invoice.status = Invoice.PENDING
                invoice.save(update_fields=['status'])


class CompanyProfile(models.Model):
    name = models.CharField(max_length=200, default="Sysnet Ventures")
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    website = models.URLField(blank=True)
    tax_number = models.CharField(max_length=50, blank=True, verbose_name="Tax/PIN Number")
    currency = models.CharField(max_length=8, default="KES", help_text="Currency code shown on documents")
    default_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Default tax % applied to new documents")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Company Profiles"

    def save(self, *args, **kwargs):
        # Singleton profile: keep exactly one row
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ContactMessage(models.Model):
    """Contact form messages from the public website"""
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Message from {self.first_name} {self.last_name}"

    def sender_name(self):
        return f"{self.first_name} {self.last_name}"
