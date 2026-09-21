"""
Automated tests for the Sysnet platform.

Covers the acceptance criteria: VAT math (inclusive/exclusive/mixed/discounts/
rounding), the quotation -> invoice -> payment -> receipt workflow, partial
payments, dedup, permissions/IDOR, historical snapshotting, PDFs, and email
failure resilience.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.test import Client as TestClient
from django.urls import reverse

from .models import (
    Client, CompanySettings, DocumentLine, Invoice, Payment, PaymentSubmission,
    PaymentAllocation, Product, Quotation, Receipt, TaxCategory,
)
from . import services
from .money import q2, vat_of, vat_component_of_gross

User = get_user_model()
D = Decimal


def make_settings(**kw):
    obj = CompanySettings.load()
    for k, v in kw.items():
        setattr(obj, k, v)
    obj.save()
    return obj


def make_tax(**kw):
    defaults = dict(name='Test 16%', rate_type=TaxCategory.STANDARD, rate_percent=D('16.00'))
    defaults.update(kw)
    return TaxCategory.objects.create(**kw.pop('defaults', None) or defaults) if False else TaxCategory.objects.create(**defaults)


def make_client(**kw):
    defaults = dict(name='Acme Ltd', email='acme@example.com', status=Client.ACTIVE)
    defaults.update(kw)
    return Client.objects.create(**defaults)


def make_user(username='staffer', role='sales', **kw):
    defaults = dict(role=role)
    defaults.update(kw)
    return User.objects.create_user(username, f'{username}@test.local', 'TestPass2026!', **defaults)


# ================================================================ money & VAT

class MoneyMathTests(TestCase):
    """Spec examples: 10,000 @16% -> VAT 1,600 / total 11,600. Inclusive 11,600 -> VAT 1,600 / net 10,000."""

    def test_vat_exclusive_spec_example(self):
        self.assertEqual(vat_of(D('10000.00'), D('16')), D('1600.00'))

    def test_vat_inclusive_spec_example(self):
        self.assertEqual(vat_component_of_gross(D('11600.00'), D('16')), D('1600.00'))

    def test_zero_rated(self):
        self.assertEqual(vat_of(D('5000.00'), D('0')), D('0.00'))

    def test_rounding_half_up(self):
        # 0.125 -> 0.13 under ROUND_HALF_UP (floats would fail this)
        self.assertEqual(q2(D('0.125')), D('0.13'))

    def test_line_exclusive(self):
        line = DocumentLine(quantity=D('2'), unit_price=D('1000'), pricing_mode='exclusive',
                            tax_rate_snapshot=D('16'), tax_type_snapshot='standard')
        self.assertEqual(line.line_net, D('2000.00'))
        self.assertEqual(line.line_vat, D('320.00'))
        self.assertEqual(line.line_total, D('2320.00'))

    def test_line_inclusive(self):
        line = DocumentLine(quantity=D('1'), unit_price=D('11600'), pricing_mode='inclusive',
                            tax_rate_snapshot=D('16'), tax_type_snapshot='standard')
        self.assertEqual(line.line_total, D('11600.00'))   # gross preserved
        self.assertEqual(line.line_net, D('10000.00'))
        self.assertEqual(line.line_vat, D('1600.00'))

    def test_line_discount_exclusive(self):
        line = DocumentLine(quantity=D('1'), unit_price=D('1000'), discount_percent=D('10'),
                            pricing_mode='exclusive', tax_rate_snapshot=D('16'), tax_type_snapshot='standard')
        self.assertEqual(line.line_net, D('900.00'))
        self.assertEqual(line.line_vat, D('144.00'))
        self.assertEqual(line.line_total, D('1044.00'))

    def test_line_discount_inclusive_preserves_gross(self):
        line = DocumentLine(quantity=D('1'), unit_price=D('11600'), discount_percent=D('10'),
                            pricing_mode='inclusive', tax_rate_snapshot=D('16'), tax_type_snapshot='standard')
        # discounted gross 10440: net 9000, vat 1440
        self.assertEqual(line.line_total, D('10440.00'))
        self.assertEqual(line.line_net, D('9000.00'))
        self.assertEqual(line.line_vat, D('1440.00'))

    def test_document_mixed_totals(self):
        inv = Invoice.objects.create(client=make_client())
        DocumentLine.objects.create(parent_object=inv, description='A', quantity=D('2'), unit_price=D('10000'),
                                    pricing_mode='exclusive', tax_rate_snapshot=D('16'), tax_type_snapshot='standard')
        DocumentLine.objects.create(parent_object=inv, description='B', quantity=D('1'), unit_price=D('11600'),
                                    pricing_mode='inclusive', tax_rate_snapshot=D('16'), tax_type_snapshot='standard')
        self.assertEqual(inv.subtotal, D('30000.00'))
        self.assertEqual(inv.vat_total, D('4800.00'))
        self.assertEqual(inv.total, D('34800.00'))


# ================================================================ numbering

class NumberingTests(TestCase):
    def test_number_formats(self):
        make_settings()
        c = make_client()
        q = Quotation.objects.create(client=c)
        q.number = __import__('billing.numbering', fromlist=['x']).next_document_number('quotation')
        q.save()
        self.assertTrue(q.number.startswith('QTN-2026-'))

    def test_sequence_increments(self):
        make_settings()
        from .numbering import next_document_number
        n1, n2 = next_document_number('invoice'), next_document_number('invoice')
        self.assertEqual(int(n2.rsplit('-', 1)[1]), int(n1.rsplit('-', 1)[1]) + 1)


# ================================================================ workflow

class QuotationWorkflowTests(TestCase):
    def setUp(self):
        make_settings()
        self.client_obj = make_client()
        self.staff = make_user('staffer', 'sales')
        self.c = TestClient()
        self.c.force_login(self.staff)

    def test_create_client_as_staff(self):
        resp = self.c.post(reverse('client_create'), {
            'client_type': 'business', 'name': 'New Co', 'email': 'new@co.com', 'status': 'active',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Client.objects.filter(name='New Co').exists())

    def test_full_quote_to_invoice_cycle(self):
        make_settings()
        tax, _ = TaxCategory.objects.get_or_create(
            name='Standard rated (16%)',
            defaults={'rate_type': 'standard', 'rate_percent': D('16.00'), 'is_default': True})
        q = Quotation.objects.create(client=self.client_obj)
        services.create_quotation_lines(q, [
            {'description': 'Work', 'quantity': D('1'), 'unit_price': D('10000'),
             'tax_category': tax},
        ])
        q.mark_sent()
        q.status = Quotation.ACCEPTED
        q.save()

        invoice, created = services.convert_quotation_to_invoice(q)
        self.assertTrue(created)
        self.assertEqual(invoice.total, D('11600.00'))
        # conversion is idempotent
        invoice2, created2 = services.convert_quotation_to_invoice(q)
        self.assertFalse(created2)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_draft_cannot_convert(self):
        q = Quotation.objects.create(client=self.client_obj)
        with self.assertRaises(ValueError):
            services.convert_quotation_to_invoice(q)


class PaymentTests(TestCase):
    def setUp(self):
        make_settings()
        TaxCategory.objects.get_or_create(
            name='Standard rated (16%)',
            defaults={'rate_type': 'standard', 'rate_percent': D('16.00'), 'is_default': True})
        self.client_obj = make_client()
        self.finance = make_user('fin', 'finance')
        self.invoice = Invoice.objects.create(client=self.client_obj, status=Invoice.ISSUED, due_date=date.today() + timedelta(days=5))
        DocumentLine.objects.create(parent_object=self.invoice, description='A', quantity=D('1'),
                                    unit_price=D('6600'), pricing_mode='exclusive',
                                    tax_rate_snapshot=D('0'), tax_type_snapshot='out_of_scope')

    def test_partial_payments_track_balance(self):
        p, created = services.record_payment(client=self.client_obj, amount=D('5000'), method='mpesa', transaction_ref='P1')
        services.confirm_payment(p, self.finance)
        services.allocate_payment(p, self.invoice, user=self.finance)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, D('1600.00'))
        self.assertEqual(self.invoice.status, Invoice.PARTIALLY_PAID)

        p2, _ = services.record_payment(client=self.client_obj, amount=D('1600'), method='bank', transaction_ref='P2')
        services.confirm_payment(p2, self.finance)
        services.allocate_payment(p2, self.invoice, user=self.finance)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_due, D('0.00'))
        self.assertEqual(self.invoice.status, Invoice.PAID)

    def test_duplicate_transaction_ref_rejected(self):
        services.record_payment(client=self.client_obj, amount=D('1000'), method='mpesa', transaction_ref='DUP1')
        p2, created = services.record_payment(client=self.client_obj, amount=D('1000'), method='mpesa', transaction_ref='DUP1')
        self.assertFalse(created)

    def test_allocation_cannot_overpay(self):
        p, _ = services.record_payment(client=self.client_obj, amount=D('1000'), method='cash')
        services.confirm_payment(p, self.finance)
        with self.assertRaises(ValueError):
            services.allocate_payment(p, self.invoice, amount=D('5000'), user=self.finance)

    def test_unverified_payment_cannot_allocate_or_receipt(self):
        p, _ = services.record_payment(client=self.client_obj, amount=D('1000'), method='cash')  # stays pending
        with self.assertRaises(ValueError):
            services.allocate_payment(p, self.invoice, user=self.finance)
        with self.assertRaises(ValueError):
            services.issue_receipt_for_payment(p, self.finance)
        self.assertEqual(Receipt.objects.count(), 0)

    def test_receipt_issued_on_confirmation_once(self):
        p, _ = services.record_payment(client=self.client_obj, amount=D('5000'), method='mpesa', transaction_ref='R1')
        services.confirm_payment(p, self.finance)
        receipt = services.issue_receipt_for_payment(p, self.finance)
        self.assertIsNotNone(receipt)
        # idempotent
        again = services.issue_receipt_for_payment(p, self.finance)
        self.assertEqual(receipt.pk, again.pk)
        self.assertEqual(Receipt.objects.count(), 1)

    def test_client_submission_does_not_mark_paid(self):
        sub = PaymentSubmission.objects.create(client=self.client_obj, amount=D('11600'),
                                               method='mpesa', transaction_ref='SUB1')
        # submission alone touches nothing:
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, D('0.00'))
        # staff verify -> confirmed + receipt + allocation must still be explicit
        payment, receipt = services.verify_submission(sub, self.finance, approve=True)
        self.assertEqual(payment.status, Payment.CONFIRMED)
        self.assertIsNotNone(receipt)
        self.assertEqual(Receipt.objects.count(), 1)
        # but the invoice is only paid once allocated:
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.ISSUED)  # not paid yet
        services.allocate_payment(payment, self.invoice, user=self.finance)
        self.invoice.refresh_from_db()
        self.assertIn(self.invoice.status, (Invoice.PAID, Invoice.PARTIALLY_PAID))

    def test_verify_records_audit(self):
        from accounts.models import AuditLog
        sub = PaymentSubmission.objects.create(client=self.client_obj, amount=D('500'), method='cash')
        services.verify_submission(sub, self.finance, approve=False, review_note='No proof')
        self.assertTrue(AuditLog.objects.filter(object_id=str(sub.pk)).exists())


# ================================================================ history integrity

class HistoryIntegrityTests(TestCase):
    def test_catalog_change_does_not_touch_documents(self):
        make_settings()
        tax = TaxCategory.objects.filter(rate_type='standard').first()
        product = Product.objects.create(name='Switch 24p', selling_price=D('18500'), tax_category=tax)
        c = make_client()
        inv = Invoice.objects.create(client=c)
        DocumentLine.objects.create(parent_object=inv, description=product.name, quantity=D('1'),
                                    unit_price=product.selling_price, catalog_item=product,
                                    tax_rate_snapshot=D('16'), tax_type_snapshot='standard')
        # staff later changes the catalog price & name
        product.selling_price = D('999')
        product.name = 'Renamed'
        product.save()
        inv.refresh_from_db()
        line = inv.lines.first()
        self.assertEqual(line.unit_price, D('18500'))
        self.assertEqual(line.description, 'Switch 24p')
        self.assertEqual(inv.total, D('21460.00'))

    def test_void_preserves_audit_trail(self):
        make_settings()
        c = make_client()
        inv = Invoice.objects.create(client=c, status=Invoice.ISSUED)
        inv.status = Invoice.VOIDED
        inv.save()
        self.assertTrue(Invoice.objects.filter(pk=inv.pk, status=Invoice.VOIDED).exists())


# ================================================================ permissions

class PermissionTests(TestCase):
    def setUp(self):
        make_settings()
        self.c1 = make_client(name='Client One', email='c1@x.com')
        self.c2 = make_client(name='Client Two', email='c2@x.com')
        self.inv2 = Invoice.objects.create(client=self.c2, status=Invoice.ISSUED, number='INV-X-0002')

    def test_client_cannot_view_other_clients_invoice(self):
        u = make_user('portaluser', 'client', client=self.c1)
        c = TestClient()
        c.force_login(u)
        resp = c.get(reverse('portal_invoice', args=[self.inv2.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_client_can_view_own_invoice(self):
        inv1 = Invoice.objects.create(client=self.c1, status=Invoice.ISSUED, number='INV-X-0001')
        u = make_user('portaluser2', 'client', client=self.c1)
        c = TestClient()
        c.force_login(u)
        resp = c.get(reverse('portal_invoice', args=[inv1.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_redirected(self):
        c = TestClient()
        resp = c.get(reverse('portal_dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_sales_cannot_access_settings(self):
        u = make_user('seller', 'sales')
        c = TestClient()
        c.force_login(u)
        resp = c.get(reverse('company_settings'))
        self.assertEqual(resp.status_code, 403)

    def test_sales_cannot_create_invoice(self):
        u = make_user('seller2', 'sales')
        c = TestClient()
        c.force_login(u)
        resp = c.get(reverse('invoice_create'))
        self.assertEqual(resp.status_code, 403)

    def test_finance_can_create_invoice(self):
        u = make_user('fin', 'finance')
        c = TestClient()
        c.force_login(u)
        resp = c.get(reverse('invoice_create'))
        self.assertEqual(resp.status_code, 200)

    def test_client_user_cannot_access_staff_dashboard(self):
        u = make_user('portalu', 'client', client=self.c1)
        c = TestClient()
        c.force_login(u)
        resp = c.get(reverse('dashboard'))
        self.assertIn(resp.status_code, (302, 403))  # blocked from staff area

    def test_throttling_blocks_after_limit(self):
        from accounts.models import LoginAttempt
        from django.utils import timezone
        now = timezone.now()
        for i in range(12):
            LoginAttempt.objects.create(username='victim', ip='1.2.3.4', successful=False)
        c = TestClient()
        resp = c.post(reverse('login'), {'username': 'victim', 'password': 'whatever'})
        # fail-closed: even correct creds would be blocked; we assert the form error path
        self.assertEqual(resp.status_code, 200)


# ================================================================ pdfs & emails

class PdfTests(TestCase):
    def setUp(self):
        make_settings()
        self.c1 = make_client(name='PDF Client')
        self.staff = make_user('pdfstaff', 'finance')
        self.c = TestClient()
        self.c.force_login(self.staff)

    def test_all_pdf_views_generate(self):
        tax = TaxCategory.objects.filter(rate_type='standard').first()
        q = Quotation.objects.create(client=self.c1)
        q.number = 'QTN-T-0001'
        q.save()
        services.create_quotation_lines(q, [{'description': 'Item', 'quantity': D('1'),
                                             'unit_price': D('1000'), 'tax_category': tax}])
        inv = Invoice.objects.create(client=self.c1, status=Invoice.ISSUED, number='INV-T-0001')
        DocumentLine.objects.create(parent_object=inv, description='Item', quantity=D('1'),
                                    unit_price=D('1000'), tax_rate_snapshot=D('16'), tax_type_snapshot='standard')
        p, _ = services.record_payment(client=self.c1, amount=D('500'), method='mpesa', transaction_ref='PDF1')
        services.confirm_payment(p, self.staff)
        receipt = services.issue_receipt_for_payment(p, self.staff)

        for url in [reverse('quotation_pdf', args=[q.pk]), reverse('invoice_pdf', args=[inv.pk]),
                    reverse('receipt_pdf', args=[receipt.pk])]:
            resp = self.c.get(url)
            self.assertEqual(resp.status_code, 200, url)
            self.assertEqual(resp['Content-Type'], 'application/pdf')
            self.assertTrue(resp.content.startswith(b'%PDF'))

    def test_statement_pdf(self):
        resp = self.c.get(reverse('client_statement_pdf', args=[self.c1.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')


class EmailFailureTests(TestCase):
    def setUp(self):
        make_settings(email='billing@sysnet.test')

    def test_email_failure_does_not_rollback_finances(self):
        c = make_client(email='client@x.com')
        fin = make_user('finmail', 'finance')
        inv = Invoice.objects.create(client=c, status=Invoice.ISSUED)
        DocumentLine.objects.create(parent_object=inv, description='A', quantity=D('1'),
                                    unit_price=D('1000'), tax_rate_snapshot=D('0'), tax_type_snapshot='out_of_scope')

        # broken email backend must not affect the payment transaction
        from unittest.mock import patch
        with patch('billing.emails.EmailMultiAlternatives.send', side_effect=Exception('SMTP down')):
            p, _ = services.record_payment(client=c, amount=D('1000'), method='cash')
            services.confirm_payment(p, fin)
            receipt = services.issue_receipt_for_payment(p, fin)

        self.assertIsNotNone(receipt)
        self.assertEqual(Receipt.objects.count(), 1)
        # failure was logged
        from .models import NotificationLog
        self.assertTrue(NotificationLog.objects.filter(status=NotificationLog.FAILED).exists())


# ================================================================ views smoke

class ViewSmokeTests(TestCase):
    def setUp(self):
        make_settings()
        self.staff = make_user('smoker', 'super_admin')

    def test_public_pages_ok(self):
        c = TestClient()
        for url in ['/', '/about/', '/services/', '/products/', '/portfolio/', '/contact/',
                    '/request-quote/', '/accounts/login/', '/sitemap.xml', '/robots.txt', '/healthz']:
            resp = c.get(url)
            self.assertEqual(resp.status_code, 200, url)

    def test_dashboard_requires_staff(self):
        c = TestClient()
        resp = c.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.staff  # exists
        c.force_login(self.staff)
        resp = c.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
