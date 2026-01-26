from django.db import models
from django.utils import timezone
from django.db.models import Sum

class Customer(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Product(models.Model):
    SERVICE = 'service'
    PRODUCT = 'product'
    TYPE_CHOICES = [
        (SERVICE, 'Service'),
        (PRODUCT, 'Product'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    product_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=SERVICE)
    
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

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Quote #{self.id} - {self.customer.name}"

    @property
    def total_amount(self):
        return self.items.aggregate(total=Sum(models.F('quantity') * models.F('unit_price')))['total'] or 0

class QuotationItem(models.Model):
    quotation = models.ForeignKey(Quotation, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    description = models.CharField(max_length=255) # Snapshot of product name or custom desc
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def total_price(self):
        return self.quantity * self.unit_price

class Invoice(models.Model):
    PENDING = 'pending'
    PAID = 'paid'
    OVERDUE = 'overdue'

    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PAID, 'Paid'),
        (OVERDUE, 'Overdue'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    quotation = models.OneToOneField(Quotation, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice #{self.id} - {self.customer.name}"
    
    @property
    def total_amount(self):
        return self.items.aggregate(total=Sum(models.F('quantity') * models.F('unit_price')))['total'] or 0
    
    @property
    def amount_paid(self):
        return self.receipts.aggregate(total=Sum('amount'))['total'] or 0

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid

class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def total_price(self):
        return self.quantity * self.unit_price

class Receipt(models.Model):
    invoice = models.ForeignKey(Invoice, related_name='receipts', on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, blank=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"Receipt #{self.id} for Invoice #{self.invoice.id}"