from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from .models import (
    Customer, Product, Quotation, QuotationItem,
    Invoice, InvoiceItem, Receipt, CompanyProfile,
)
from .numbering import next_document_number


def make_company(**kwargs):
    defaults = dict(name='Sysnet Ventures', currency='KES', default_tax_rate=Decimal('16.00'))
    defaults.update(kwargs)
    return CompanyProfile.objects.create(**defaults)


def make_customer(**kwargs):
    defaults = dict(name='Acme Ltd', email='acme@example.com', phone='+254700000000')
    defaults.update(kwargs)
    return Customer.objects.create(**defaults)


def make_product(**kwargs):
    defaults = dict(name='CCTV Install', price=Decimal('15000.00'), product_type='service')
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


class NumberingTests(TestCase):
    def test_invoice_numbers_sequential(self):
        c = make_customer()
        for i in range(1, 4):
            inv = Invoice.objects.create(customer=c)
            year = date.today().year
            self.assertEqual(inv.number, f'INV-{year}-{i:04d}')

    def test_quotation_and_receipt_prefixes(self):
        c = make_customer()
        q = Quotation.objects.create(customer=c)
        inv = Invoice.objects.create(customer=c)
        r = Receipt.objects.create(invoice=inv, amount=Decimal('10.00'))
        year = date.today().year
        self.assertTrue(q.number.startswith('QTN-'))
        self.assertTrue(r.number.startswith('RCP-'))
        self.assertTrue(r.number.endswith('-0001'))

    def test_concurrent_safety_uses_max(self):
        c = make_customer()
        Invoice.objects.create(customer=c)  # INV-...-0001
        Invoice.objects.create(customer=c)  # INV-...-0002
        self.assertEqual(next_document_number(Invoice).endswith('0003'), True)


class MoneyMathTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.customer = make_customer()
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            tax_rate=Decimal('16.00'),
            due_date=date.today() + timedelta(days=10),
        )
        InvoiceItem.objects.create(invoice=self.invoice, description='A', quantity=2, unit_price=Decimal('1000.00'))
        InvoiceItem.objects.create(invoice=self.invoice, description='B', quantity=1, unit_price=Decimal('500.00'))

    def test_subtotal_tax_total(self):
        self.assertEqual(self.invoice.subtotal, Decimal('2500.00'))
        self.assertEqual(self.invoice.tax_amount, Decimal('400.00'))
        self.assertEqual(self.invoice.total_amount, Decimal('2900.00'))
        self.assertEqual(self.invoice.balance_due, Decimal('2900.00'))

    def test_partial_payment_progress(self):
        Receipt.objects.create(invoice=self.invoice, amount=Decimal('1000.00'))
        self.assertEqual(self.invoice.amount_paid, Decimal('1000.00'))
        self.assertEqual(self.invoice.balance_due, Decimal('1900.00'))
        self.assertEqual(self.invoice.payment_progress, 34)

    def test_mark_paid_if_settled(self):
        Receipt.objects.create(invoice=self.invoice, amount=Decimal('2900.00'))
        self.assertTrue(self.invoice.mark_paid_if_settled())
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PAID)
        # idempotent
        self.assertFalse(self.invoice.mark_paid_if_settled())

    def test_overdue_effective_status(self):
        self.invoice.status = Invoice.PENDING
        self.invoice.due_date = date.today() - timedelta(days=1)
        self.assertEqual(self.invoice.effective_status, Invoice.OVERDUE)
        self.invoice.status = Invoice.PAID
        self.assertEqual(self.invoice.effective_status, Invoice.PAID)

    def test_receipt_delete_restores_status(self):
        Receipt.objects.create(invoice=self.invoice, amount=Decimal('2900.00'))
        self.invoice.mark_paid_if_settled()
        self.invoice.refresh_from_db()
        receipt = self.invoice.receipts.first()
        receipt.delete()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.PENDING)

    def test_quotation_totals(self):
        q = Quotation.objects.create(customer=self.customer, tax_rate=Decimal('16.00'))
        QuotationItem.objects.create(quotation=q, description='X', quantity=3, unit_price=Decimal('100.00'))
        self.assertEqual(q.subtotal, Decimal('300.00'))
        self.assertEqual(q.tax_amount, Decimal('48.00'))
        self.assertEqual(q.total_amount, Decimal('348.00'))


class CompanyProfileTests(TestCase):
    def test_singleton_load(self):
        make_company()
        again = CompanyProfile.load()
        self.assertEqual(CompanyProfile.objects.count(), 1)
        self.assertEqual(again.name, 'Sysnet Ventures')
        # saving the same instance keeps one row
        again.name = 'Renamed'
        again.save()
        self.assertEqual(CompanyProfile.objects.count(), 1)


class FlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='tester', password='testpass123')
        self.client.login(username='tester', password='testpass123')
        make_company()
        self.customer = make_customer()
        self.product = make_product()

    def _quote_post_data(self, **overrides):
        data = {
            'customer': self.customer.pk,
            'date': date.today().isoformat(),
            'valid_until': (date.today() + timedelta(days=30)).isoformat(),
            'status': Quotation.SENT,
            'tax_rate': '16.00',
            'notes': 'Test notes',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': self.product.pk,
            'items-0-description': 'CCTV Install',
            'items-0-quantity': '2',
            'items-0-unit_price': '15000.00',
        }
        data.update(overrides)
        return data

    def test_quotation_create(self):
        resp = self.client.post(reverse('quotation_create'), self._quote_post_data())
        self.assertEqual(Quotation.objects.count(), 1)
        quote = Quotation.objects.first()
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/billing/quotation/{quote.pk}/', resp.url)
        self.assertEqual(quote.items.count(), 1)
        self.assertEqual(quote.total_amount, Decimal('34800.00'))  # 30000 + 16%

    def test_convert_quote_to_invoice(self):
        quote = Quotation.objects.create(
            customer=self.customer, status=Quotation.SENT,
            tax_rate=Decimal('16.00'), date=date.today(),
        )
        QuotationItem.objects.create(quotation=quote, product=self.product, description='CCTV', quantity=1, unit_price=Decimal('15000.00'))

        resp = self.client.post(reverse('convert_quote_to_invoice', args=[quote.pk]))
        self.assertEqual(resp.status_code, 302)
        quote.refresh_from_db()
        self.assertEqual(quote.status, Quotation.ACCEPTED)
        invoice = Invoice.objects.get(quotation=quote)
        self.assertEqual(invoice.items.count(), 1)
        self.assertEqual(invoice.tax_rate, quote.tax_rate)
        self.assertEqual(invoice.status, Invoice.PENDING)

    def test_convert_twice_is_blocked(self):
        quote = Quotation.objects.create(customer=self.customer, status=Quotation.SENT, date=date.today())
        QuotationItem.objects.create(quotation=quote, description='X', quantity=1, unit_price=Decimal('100.00'))
        self.client.post(reverse('convert_quote_to_invoice', args=[quote.pk]))
        self.client.post(reverse('convert_quote_to_invoice', args=[quote.pk]))
        self.assertEqual(Invoice.objects.count(), 1)

    def test_convert_draft_blocked(self):
        quote = Quotation.objects.create(customer=self.customer, status=Quotation.DRAFT, date=date.today())
        QuotationItem.objects.create(quotation=quote, description='X', quantity=1, unit_price=Decimal('100.00'))
        resp = self.client.post(reverse('convert_quote_to_invoice', args=[quote.pk]))
        self.assertEqual(Invoice.objects.count(), 0)

    def test_invoice_create_view(self):
        data = {
            'customer': self.customer.pk,
            'date': date.today().isoformat(),
            'due_date': (date.today() + timedelta(days=14)).isoformat(),
            'status': Invoice.PENDING,
            'tax_rate': '0',
            'notes': '',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': self.product.pk,
            'items-0-description': 'Work',
            'items-0-quantity': '1',
            'items-0-unit_price': '999.99',
        }
        resp = self.client.post(reverse('invoice_create'), data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Invoice.objects.count(), 1)
        inv = Invoice.objects.first()
        self.assertEqual(inv.total_amount, Decimal('999.99'))

    def test_invoice_requires_items(self):
        data = {
            'customer': self.customer.pk,
            'date': date.today().isoformat(),
            'due_date': (date.today() + timedelta(days=14)).isoformat(),
            'status': Invoice.PENDING,
            'tax_rate': '0',
            'notes': '',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': '',
            'items-0-description': '',
            'items-0-quantity': '1',
            'items-0-unit_price': '',
        }
        resp = self.client.post(reverse('invoice_create'), data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_record_payment_and_full_settlement(self):
        invoice = Invoice.objects.create(customer=self.customer, due_date=date.today() + timedelta(days=10))
        InvoiceItem.objects.create(invoice=invoice, description='A', quantity=1, unit_price=Decimal('2000.00'))
        resp = self.client.post(reverse('add_receipt', args=[invoice.pk]), {
            'date': date.today().isoformat(),
            'amount': '2000.00',
            'payment_method': 'M-Pesa',
            'reference': 'QX12YR90',
            'note': '',
        })
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.PAID)
        self.assertEqual(Receipt.objects.count(), 1)
        self.assertTrue(Receipt.objects.first().number.startswith('RCP-'))

    def test_receipt_delete_view(self):
        invoice = Invoice.objects.create(customer=self.customer)
        InvoiceItem.objects.create(invoice=invoice, description='A', quantity=1, unit_price=Decimal('500.00'))
        receipt = Receipt.objects.create(invoice=invoice, amount=Decimal('500.00'))
        invoice.mark_paid_if_settled()
        resp = self.client.post(reverse('receipt_delete', args=[receipt.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Receipt.objects.count(), 0)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.PENDING)

    def test_invoice_list_filters(self):
        c1 = make_customer(name='One')
        Invoice.objects.create(customer=c1, status=Invoice.PAID)
        Invoice.objects.create(customer=c1, status=Invoice.PENDING)
        resp = self.client.get(reverse('invoice_list'), {'status': 'paid'})
        self.assertContains(resp, 'Invoices')
        # only one row (plus header) -> the paid invoice number appears
        self.assertContains(resp, Invoice.objects.filter(status=Invoice.PAID).first().number)

    def test_dashboard_requires_login(self):
        anon = Client()
        resp = anon.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_pdf_views_generate(self):
        quote = Quotation.objects.create(customer=self.customer, status=Quotation.SENT, date=date.today(), tax_rate=Decimal('16.00'))
        QuotationItem.objects.create(quotation=quote, description='X', quantity=1, unit_price=Decimal('100.00'))
        invoice = Invoice.objects.create(customer=self.customer, tax_rate=Decimal('16.00'), due_date=date.today() + timedelta(days=5))
        InvoiceItem.objects.create(invoice=invoice, description='Y', quantity=2, unit_price=Decimal('250.00'))
        Receipt.objects.create(invoice=invoice, amount=Decimal('100.00'))

        for url, name in [
            (reverse('quotation_pdf', args=[quote.pk]), quote.number),
            (reverse('invoice_pdf', args=[invoice.pk]), invoice.number),
        ]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, f'PDF failed for {name}')
            self.assertEqual(resp['Content-Type'], 'application/pdf')

        resp = self.client.get(reverse('receipt_pdf', args=[Receipt.objects.first().pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')

    def test_product_api(self):
        resp = self.client.get(reverse('product_api', args=[self.product.pk]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['name'], 'CCTV Install')
        self.assertEqual(data['price'], '15000.00')

    def test_customer_ajax_create(self):
        resp = self.client.post(reverse('customer_create_modal'), {
            'name': 'Ajax Co', 'email': 'ajax@co.com', 'phone': '', 'address': '',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(Customer.objects.filter(name='Ajax Co').exists())

    def test_customer_delete_blocked_with_documents(self):
        inv = Invoice.objects.create(customer=self.customer)
        InvoiceItem.objects.create(invoice=inv, description='A', quantity=1, unit_price=Decimal('10.00'))
        resp = self.client.post(reverse('customer_delete', args=[self.customer.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_customer_delete_allowed_without_documents(self):
        orphan = make_customer(name='Orphan')
        resp = self.client.post(reverse('customer_delete', args=[orphan.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Customer.objects.filter(pk=orphan.pk).exists())

    def test_contact_message_flow(self):
        from .models import ContactMessage
        ContactMessage.objects.create(first_name='Jane', last_name='Doe', email='jane@x.com', message='Hi')
        resp = self.client.get(reverse('message_list'))
        self.assertContains(resp, 'Jane')
        msg = ContactMessage.objects.first()
        self.client.get(reverse('message_detail', args=[msg.pk]))
        msg.refresh_from_db()
        self.assertTrue(msg.is_read)
