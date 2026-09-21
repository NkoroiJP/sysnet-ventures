"""Public + staff forms for the billing app."""
from decimal import Decimal

from django import forms

from .models import (
    CompanySettings, TaxCategory, Client, ClientContact, Product,
    ServiceEnquiry, ContactMessage, PaymentSubmission, Payment,
)
from .storage import validate_upload

INPUT_CLASS = 'input'


def _style(form):
    for field in form.fields.values():
        css = field.widget.attrs.get('class', '')
        field.widget.attrs['class'] = (css + ' ' + INPUT_CLASS).strip()


# ---------------------------------------------------------------- public forms

class ServiceEnquiryForm(forms.ModelForm):
    services_text = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        help_text='Comma-separated list of selected services.',
    )

    class Meta:
        model = ServiceEnquiry
        fields = ['name', 'email', 'phone', 'company', 'message']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describe your requirements…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)
        self.fields['phone'].required = False
        self.fields['company'].required = False

    def save(self, commit=True):
        obj = super().save(commit=False)
        raw = self.cleaned_data.get('services_text') or ''
        obj.services = [s.strip() for s in raw.split(',') if s.strip()]
        if commit:
            obj.save()
        return obj


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'phone', 'category', 'message']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)
        self.fields['phone'].required = False


class PaymentSubmissionForm(forms.ModelForm):
    evidence = forms.FileField(
        required=False,
        help_text='Optional: upload a screenshot or PDF of your payment confirmation (max 5 MB).',
    )

    class Meta:
        model = PaymentSubmission
        fields = ['amount', 'method', 'transaction_ref', 'paid_on', 'note', 'evidence']
        widgets = {
            'paid_on': forms.DateInput(attrs={'type': 'date'}),
            'note': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)

    def clean_evidence(self):
        f = self.cleaned_data.get('evidence')
        if f:
            validate_upload(f)
        return f


# ---------------------------------------------------------------- staff forms

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'client_type', 'name', 'contact_person', 'email', 'phone',
            'billing_address', 'delivery_address', 'kra_pin', 'vat_details', 'notes', 'status',
        ]
        widgets = {
            'billing_address': forms.Textarea(attrs={'rows': 2}),
            'delivery_address': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)


class ClientContactForm(forms.ModelForm):
    class Meta:
        model = ClientContact
        fields = ['name', 'email', 'phone', 'is_primary']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'sku', 'category', 'description', 'unit', 'selling_price',
            'tax_category', 'is_active', 'track_stock', 'stock_quantity', 'public_show', 'image',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)
        self.fields['selling_price'].widget.attrs.update({'step': '0.01', 'min': '0'})

    def clean_stock_quantity(self):
        qty = self.cleaned_data.get('stock_quantity')
        if self.cleaned_data.get('track_stock') and qty is not None and qty < 0:
            raise forms.ValidationError('Stock quantity cannot be negative.')
        return qty


class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        fields = [
            'name', 'tagline', 'logo', 'phone', 'whatsapp_number', 'email', 'website',
            'physical_address', 'postal_address', 'kra_pin', 'vat_registered', 'vat_number',
            'currency', 'quotation_prefix', 'invoice_prefix', 'receipt_prefix', 'credit_note_prefix',
            'quotation_validity_days', 'invoice_payment_terms_days', 'payment_instructions',
            'document_footer', 'terms_and_conditions', 'default_tax_category',
            'brand_primary', 'brand_accent',
        ]
        widgets = {
            'physical_address': forms.Textarea(attrs={'rows': 2}),
            'postal_address': forms.Textarea(attrs={'rows': 2}),
            'payment_instructions': forms.Textarea(attrs={'rows': 3}),
            'document_footer': forms.Textarea(attrs={'rows': 2}),
            'terms_and_conditions': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)


class TaxCategoryForm(forms.ModelForm):
    class Meta:
        model = TaxCategory
        fields = ['name', 'rate_type', 'rate_percent', 'effective_from', 'effective_to', 'is_default', 'is_active']
        widgets = {
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
            'effective_to': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)


class PaymentRecordForm(forms.Form):
    """Staff recording a payment received outside the portal."""
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    method = forms.ChoiceField(choices=Payment.METHOD_CHOICES)
    transaction_ref = forms.CharField(max_length=100, required=False)
    paid_on = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)
