from django.contrib import admin
from .models import Customer, Product, Quotation, QuotationItem, Invoice, InvoiceItem, Receipt, CompanyProfile

@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'website')

    def has_add_permission(self, request):
        if CompanyProfile.objects.exists():
            return False
        return super().has_add_permission(request)

class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 1

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1

class ReceiptInline(admin.TabularInline):
    model = Receipt
    extra = 0

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'created_at')
    search_fields = ('name', 'email')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_type', 'price')
    list_filter = ('product_type',)

@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'date', 'total_amount', 'status')
    list_filter = ('status', 'date')
    inlines = [QuotationItemInline]
    actions = ['convert_to_invoice']

    def convert_to_invoice(self, request, queryset):
        for quote in queryset:
            if not hasattr(quote, 'invoice'):
                invoice = Invoice.objects.create(
                    customer=quote.customer,
                    quotation=quote,
                    date=quote.date, # or timezone.now()
                    status=Invoice.PENDING
                )
                # Copy items
                for item in quote.items.all():
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        product=item.product,
                        description=item.description,
                        quantity=item.quantity,
                        unit_price=item.unit_price
                    )
        self.message_user(request, "Selected quotations converted to invoices.")
    convert_to_invoice.short_description = "Convert selected to Invoice"

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'date', 'total_amount', 'amount_paid', 'status')
    list_filter = ('status', 'date')
    inlines = [InvoiceItemInline, ReceiptInline]

@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoice', 'date', 'amount', 'payment_method')
    list_filter = ('date', 'payment_method')