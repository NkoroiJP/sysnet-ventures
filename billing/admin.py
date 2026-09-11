from django.contrib import admin

from .models import (
    Customer, Product, Quotation, QuotationItem,
    Invoice, InvoiceItem, Receipt, CompanyProfile,
)


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'website', 'currency', 'default_tax_rate')

    def has_add_permission(self, request):
        return not CompanyProfile.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


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
    list_display = ('name', 'product_type', 'price', 'is_active')
    list_filter = ('product_type', 'is_active')


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ('number', 'customer', 'date', 'valid_until', 'subtotal', 'tax_rate', 'total_amount', 'status')
    list_filter = ('status', 'date')
    search_fields = ('number', 'customer__name')
    inlines = [QuotationItemInline]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('number', 'customer', 'date', 'due_date', 'subtotal', 'tax_rate', 'total_amount', 'amount_paid', 'status')
    list_filter = ('status', 'date')
    search_fields = ('number', 'customer__name')
    inlines = [InvoiceItemInline, ReceiptInline]
    actions = ['mark_overdue']

    @admin.action(description='Mark selected pending invoices as overdue')
    def mark_overdue(self, request, queryset):
        updated = queryset.filter(status=Invoice.PENDING).update(status=Invoice.OVERDUE)
        self.message_user(request, f'{updated} invoice(s) marked overdue.')


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('number', 'invoice', 'date', 'amount', 'payment_method', 'reference')
    list_filter = ('date', 'payment_method')
    search_fields = ('number', 'invoice__number', 'reference')
