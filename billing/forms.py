from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.utils import timezone

from .models import Customer, Quotation, QuotationItem, Invoice, InvoiceItem, Receipt, Product, CompanyProfile

INPUT_CLASS = 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 sm:text-sm'


def style(widget):
    existing = widget.attrs.get('class', '')
    widget.attrs['class'] = (existing + ' ' + INPUT_CLASS).strip()


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'email', 'phone', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Full name or company'}),
            'email': forms.EmailInput(attrs={'placeholder': 'name@example.com'}),
            'phone': forms.TextInput(attrs={'placeholder': '+254 7xx xxx xxx'}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            style(field.widget)


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ['customer', 'date', 'valid_until', 'status', 'tax_rate', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Payment terms, scope notes...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company = CompanyProfile.load()
        self.fields['tax_rate'].initial = company.default_tax_rate
        self.fields['tax_rate'].help_text = 'Applied to subtotal (%)'
        self.fields['customer'].widget.attrs.update({'class': 'js-customer-select'})
        if not self.instance.pk:
            self.fields['date'].initial = timezone.localdate()
            self.fields['valid_until'].initial = timezone.localdate() + timezone.timedelta(days=30)
        for field in self.fields.values():
            style(field.widget)


class QuotationItemForm(forms.ModelForm):
    class Meta:
        model = QuotationItem
        fields = ['product', 'description', 'quantity', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={'class': 'product-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        self.fields['product'].required = False
        self.fields['quantity'].widget.attrs.update({'min': 1, 'class': 'js-qty'})
        self.fields['unit_price'].widget.attrs.update({'step': '0.01', 'min': 0, 'class': 'js-price'})
        for field in self.fields.values():
            style(field.widget)


class QuotationItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        has_items = False
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or form.cleaned_data.get('DELETE'):
                continue
            if form.cleaned_data.get('description') and form.cleaned_data.get('unit_price') is not None:
                has_items = True
        if not has_items:
            raise forms.ValidationError('Add at least one line item before saving.')


QuotationItemFormSet = inlineformset_factory(
    Quotation, QuotationItem, form=QuotationItemForm, formset=QuotationItemFormSet,
    fields=['product', 'description', 'quantity', 'unit_price'],
    extra=3, can_delete=True,
)


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['customer', 'date', 'due_date', 'status', 'tax_rate', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Payment instructions, bank details...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company = CompanyProfile.load()
        self.fields['tax_rate'].initial = company.default_tax_rate
        self.fields['tax_rate'].help_text = 'Applied to subtotal (%)'
        if not self.instance.pk:
            self.fields['date'].initial = timezone.localdate()
            self.fields['due_date'].initial = timezone.localdate() + timezone.timedelta(days=30)
        for field in self.fields.values():
            style(field.widget)


class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ['product', 'description', 'quantity', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={'class': 'product-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        self.fields['product'].required = False
        self.fields['quantity'].widget.attrs.update({'min': 1, 'class': 'js-qty'})
        self.fields['unit_price'].widget.attrs.update({'step': '0.01', 'min': 0, 'class': 'js-price'})
        for field in self.fields.values():
            style(field.widget)


class InvoiceItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        has_items = False
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or form.cleaned_data.get('DELETE'):
                continue
            if form.cleaned_data.get('description') and form.cleaned_data.get('unit_price') is not None:
                has_items = True
        if not has_items:
            raise forms.ValidationError('Add at least one line item before saving.')


InvoiceItemFormSet = inlineformset_factory(
    Invoice, InvoiceItem, form=InvoiceItemForm, formset=InvoiceItemFormSet,
    fields=['product', 'description', 'quantity', 'unit_price'],
    extra=3, can_delete=True,
)


class ReceiptForm(forms.ModelForm):
    class Meta:
        model = Receipt
        fields = ['date', 'amount', 'payment_method', 'reference', 'note']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'reference': forms.TextInput(attrs={'placeholder': 'e.g. M-Pesa code, cheque no.'}),
            'note': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].initial = timezone.localdate()
        self.fields['amount'].widget.attrs.update({'step': '0.01', 'min': 0})
        self.fields['payment_method'].widget.attrs.update({'class': 'js-payment-method'})
        if invoice is not None:
            self.fields['amount'].initial = invoice.balance_due
        for field in self.fields.values():
            style(field.widget)

    def clean(self):
        cleaned = super().clean()
        invoice = self.cleaned_data.get('invoice') or getattr(self, '_invoice_hint', None)
        amount = cleaned.get('amount')
        if invoice and amount and amount <= 0:
            self.add_error('amount', 'Amount must be greater than zero.')
        return cleaned


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'price', 'product_type', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].widget.attrs.update({'step': '0.01', 'min': 0})
        for field in self.fields.values():
            style(field.widget)


class CompanyProfileForm(forms.ModelForm):
    class Meta:
        model = CompanyProfile
        fields = ['name', 'logo', 'email', 'phone', 'address', 'website', 'tax_number', 'currency', 'default_tax_rate']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['default_tax_rate'].widget.attrs.update({'step': '0.01', 'min': 0})
        for field in self.fields.values():
            style(field.widget)


class CustomerSearchForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Search customers...', 'class': 'js-search-input'}))
