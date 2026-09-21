"""Dynamic document builder forms — parse editable line-item grids from POST."""
from django import forms

from .models import Client, TaxCategory
from .money import q2, ZERO
from .validators import validate_line_data


class DocumentBuilderForm(forms.Form):
    """Shared logic for quotation/invoice builders. Subclasses set prefix fields."""

    client = forms.ModelChoiceField(queryset=Client.objects.all(), label='Client')
    issue_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))
    terms = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))
    delivery_info = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parse_lines()
        for name in ('client', 'issue_date'):
            css = self.fields[name].widget.attrs.get('class', '')
            self.fields[name].widget.attrs['class'] = (css + ' input').strip()

    # ---- line parsing --------------------------------------------------
    def _parse_lines(self):
        """Pull lines-N-* fields from data (bound) or seed two blanks (unbound)."""
        data = getattr(self, 'data', None)
        self.lines_data = []
        self.line_errors = []

        if data:
            count = int(data.get('lines-count', '0') or 0)
            for i in range(min(count, 100)):
                prefix = f'lines-{i}-'
                desc = (data.get(prefix + 'description') or '').strip()
                qty = data.get(prefix + 'quantity') or ''
                price = data.get(prefix + 'unit_price') or ''
                if not desc and not qty and not price:
                    continue  # skip fully empty rows
                self.lines_data.append({
                    'description': desc,
                    'unit': (data.get(prefix + 'unit') or '').strip(),
                    'quantity': qty,
                    'unit_price': price,
                    'pricing_mode': data.get(prefix + 'pricing_mode') or 'exclusive',
                    'discount_percent': data.get(prefix + 'discount_percent') or '0',
                    'tax_category': data.get(prefix + 'tax_category') or None,
                    'catalog_item_id': data.get(prefix + 'catalog_item_id') or None,
                    'line_order': i,
                })
        else:
            self.lines_data = [self._blank_line(), self._blank_line()]

    def _blank_line(self):
        return {
            'description': '', 'unit': '', 'quantity': '', 'unit_price': '',
            'pricing_mode': 'exclusive', 'discount_percent': '0',
            'tax_category': None, 'catalog_item_id': None, 'line_order': 0,
        }

    def clean(self):
        cleaned = super().clean()
        if not self.lines_data:
            raise forms.ValidationError('Add at least one line item.')
        errors = validate_line_data(self.lines_data)
        if errors:
            raise forms.ValidationError(errors[0])
        return cleaned

    def cleaned_lines(self):
        """Normalized line dicts ready for services.create_quotation_lines."""
        result = []
        for ln in self.lines_data:
            tax_cat = None
            if ln.get('tax_category'):
                try:
                    tax_cat = TaxCategory.objects.get(pk=ln['tax_category'])
                except (TaxCategory.DoesNotExist, ValueError, TypeError):
                    tax_cat = None
            result.append({
                'description': ln['description'],
                'unit': ln['unit'],
                'quantity': q2(ln['quantity']),
                'unit_price': q2(ln['unit_price']),
                'pricing_mode': ln['pricing_mode'] if ln['pricing_mode'] in ('exclusive', 'inclusive') else 'exclusive',
                'discount_percent': q2(ln['discount_percent'] or 0),
                'tax_category': tax_cat,
                'catalog_item_id': ln.get('catalog_item_id') or None,
                'line_order': ln['line_order'],
            })
        return result


class QuotationBuilderForm(DocumentBuilderForm):
    valid_until = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))


class InvoiceBuilderForm(DocumentBuilderForm):
    due_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
