from django.contrib import admin

from .models import (
    CompanySettings, TaxCategory, Client, ClientContact, Product,
    DocumentLine, Quotation, Invoice, CreditNote, Payment, PaymentSubmission,
    PaymentAllocation, Receipt, NotificationLog, ContactMessage,
)


@admin.register(CompanySettings)
class CompanySettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not CompanySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TaxCategory)
class TaxCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'rate_type', 'rate_percent', 'effective_from', 'effective_to', 'is_default', 'is_active')
    list_filter = ('rate_type', 'is_active')


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'client_type', 'email', 'phone', 'status', 'created_at')
    list_filter = ('client_type', 'status')
    search_fields = ('name', 'email', 'phone')


admin.site.register([ClientContact, DocumentLine, PaymentAllocation])


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ('number', 'client', 'status', 'issue_date', 'valid_until', 'total')
    list_filter = ('status',)
    search_fields = ('number', 'client__name')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('number', 'client', 'status', 'issue_date', 'due_date', 'total', 'balance_due')
    list_filter = ('status',)
    search_fields = ('number', 'client__name')


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ('number', 'client', 'invoice', 'reason', 'amount', 'applied_to_invoice')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('number', 'client', 'amount', 'method', 'transaction_ref', 'status', 'paid_on')
    list_filter = ('status', 'method')


@admin.register(PaymentSubmission)
class PaymentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('client', 'amount', 'method', 'transaction_ref', 'status', 'created_at')
    list_filter = ('status', 'method')


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('number', 'client', 'amount', 'payment', 'issued_at')


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'purpose', 'recipient', 'status', 'attempts')
    list_filter = ('status', 'purpose')
    readonly_fields = [f.name for f in NotificationLog._meta.fields]


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'category', 'is_read', 'created_at')
    list_filter = ('category', 'is_read')
