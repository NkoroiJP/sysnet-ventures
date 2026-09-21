"""Client portal views — self-service, strictly scoped to the logged-in client."""
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.audit import audit
from .access import client_of_required
from .emails import notify_payment_confirmed
from .forms import PaymentSubmissionForm
from .models import (
    Quotation, Invoice, Payment, PaymentSubmission, Receipt, CompanySettings,
    ServiceEnquiry,
)
from . import services


def _portal_client(request):
    """Resolve the Client record for the logged-in portal user (IDOR guard)."""
    user = request.user
    if not user.is_authenticated:
        return None
    if user.is_client and user.client_id:
        return user.client
    return None


def portal_required(view):
    from functools import wraps

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if request.user.is_staff_user or request.user.is_superuser:
            # staff may preview the portal but get redirected to the dashboard
            return redirect('dashboard')
        if not _portal_client(request):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return _wrapped


@portal_required
def portal_dashboard(request):
    client = _portal_client(request)
    invoices = client.invoices.exclude(status=Invoice.VOIDED).order_by('-issue_date')
    return render(request, 'billing/portal/dashboard.html', {
        'client': client,
        'quotations': client.quotations.exclude(status=Quotation.DRAFT).order_by('-issue_date')[:6],
        'invoices': invoices[:6],
        'outstanding': client.outstanding,
        'overdue_amount': client.overdue_amount,
        'overdue_invoices': [i for i in invoices if i.effective_status == Invoice.OVERDUE],
        'payments': client.payments.filter(status=Payment.CONFIRMED).order_by('-paid_on')[:5],
        'pending_submissions': client.payment_submissions.filter(status=Payment.PENDING),
    })


@portal_required
@client_of_required(Quotation)
def portal_quotation(request, pk):
    quotation = get_object_or_404(Quotation.objects.select_related('client'), pk=pk)
    if quotation.client_id != request.user.client_id:
        raise PermissionDenied
    quotation.mark_viewed()
    return render(request, 'billing/portal/quotation_detail.html', {
        'quotation': quotation, 'lines': quotation.lines,
    })


@portal_required
@require_POST
def portal_quotation_decide(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if not request.user.is_client or quotation.client_id != request.user.client_id:
        raise PermissionDenied
    decision = request.POST.get('decision')
    note = request.POST.get('note', '')

    if quotation.effective_status not in (Quotation.SENT, Quotation.VIEWED):
        messages.error(request, 'This quotation is no longer open for a decision.')
        return redirect('portal_quotation', pk=pk)

    if decision == 'accept':
        quotation.status = Quotation.ACCEPTED
        quotation.decided_at = timezone.now()
        quotation.decision_note = note
        quotation.save(update_fields=['status', 'decided_at', 'decision_note'])
        audit('status', quotation, user=request.user, detail='accepted by client')
        messages.success(request, 'Quotation accepted. Our team will prepare your invoice.')
    elif decision == 'reject':
        quotation.status = Quotation.REJECTED
        quotation.decided_at = timezone.now()
        quotation.decision_note = note
        quotation.save(update_fields=['status', 'decided_at', 'decision_note'])
        audit('status', quotation, user=request.user, detail='rejected by client')
        messages.info(request, 'Quotation rejected. Thank you for the feedback.')
    elif decision == 'revise':
        audit('status', quotation, user=request.user, detail='revision requested by client')
        messages.success(request, 'Revision request sent to our team.')
    from .emails import notify_quotation_decision
    if decision in ('accept', 'reject'):
        notify_quotation_decision(quotation, accepted=(decision == 'accept'))
    return redirect('portal_quotation', pk=pk)


@portal_required
@client_of_required(Quotation)
def portal_quotation_pdf(request, pk):
    from .views_documents import render_pdf, _pdf
    quotation = get_object_or_404(Quotation.objects.select_related('client'), pk=pk)
    if quotation.client_id != request.user.client_id:
        raise PermissionDenied
    pdf = render_pdf('billing/pdf_quotation.html', {
        'quotation': quotation, 'lines': quotation.lines, 'company': CompanySettings.load(),
    })
    if not pdf:
        return HttpResponse('Error generating PDF', status=500)
    return _pdf(pdf, f'{quotation.number}.pdf')


@portal_required
@client_of_required(Invoice)
def portal_invoice(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related('client'), pk=pk)
    if invoice.client_id != request.user.client_id:
        raise PermissionDenied
    return render(request, 'billing/portal/invoice_detail.html', {
        'invoice': invoice, 'lines': invoice.lines,
        'allocations': invoice.allocations.select_related('payment'),
    })


@portal_required
@client_of_required(Invoice)
def portal_invoice_pdf(request, pk):
    from .views_documents import render_pdf, _pdf
    invoice = get_object_or_404(Invoice.objects.select_related('client'), pk=pk)
    if invoice.client_id != request.user.client_id:
        raise PermissionDenied
    pdf = render_pdf('billing/pdf_invoice.html', {
        'invoice': invoice, 'lines': invoice.lines, 'company': CompanySettings.load(),
    })
    if not pdf:
        return HttpResponse('Error generating PDF', status=500)
    return _pdf(pdf, f'{invoice.number}.pdf')


@portal_required
def portal_submit_payment(request):
    client = _portal_client(request)
    if request.method == 'POST':
        form = PaymentSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.client = client
            sub.status = Payment.PENDING
            sub.save()
            audit('payment', sub, user=request.user, detail='payment reference submitted')
            messages.success(request, 'Payment reference submitted. We will verify it and issue a receipt shortly.')
            return redirect('portal_payments')
    else:
        form = PaymentSubmissionForm()
    return render(request, 'billing/portal/payment_submit.html', {
        'form': form, 'client': client,
    })


@portal_required
def portal_payments(request):
    client = _portal_client(request)
    return render(request, 'billing/portal/payments.html', {
        'client': client,
        'payments': client.payments.filter(status__in=[Payment.CONFIRMED, Payment.VERIFIED]).order_by('-paid_on'),
        'submissions': client.payment_submissions.order_by('-created_at'),
        'open_invoices': [i for i in client.invoices.exclude(status__in=[Invoice.VOIDED, Invoice.DRAFT]) if i.balance_due > 0],
    })


@portal_required
@client_of_required(Receipt)
def portal_receipt(request, pk):
    receipt = get_object_or_404(Receipt.objects.select_related('payment', 'client'), pk=pk)
    if receipt.client_id != request.user.client_id:
        raise PermissionDenied
    return render(request, 'billing/portal/receipt_detail.html', {'receipt': receipt})


@portal_required
@client_of_required(Receipt)
def portal_receipt_pdf(request, pk):
    from .views_documents import render_pdf, _pdf
    receipt = get_object_or_404(Receipt.objects.select_related('payment', 'client'), pk=pk)
    if receipt.client_id != request.user.client_id:
        raise PermissionDenied
    pdf = render_pdf('billing/pdf_receipt.html', {
        'receipt': receipt,
        'allocations': receipt.payment.allocations.select_related('invoice'),
        'company': CompanySettings.load(),
    })
    if not pdf:
        return HttpResponse('Error generating PDF', status=500)
    return _pdf(pdf, f'{receipt.number}.pdf')


@portal_required
def portal_statement(request):
    client = _portal_client(request)
    entries = services.client_statement(client)
    return render(request, 'billing/portal/statement.html', {
        'client': client, 'entries': entries, 'company': CompanySettings.load(),
    })


@portal_required
def portal_statement_pdf(request):
    from .views_documents import render_pdf, _pdf
    client = _portal_client(request)
    entries = services.client_statement(client)
    pdf = render_pdf('billing/pdf_statement.html', {
        'client': client, 'entries': entries, 'company': CompanySettings.load(),
        'date_from': None, 'date_to': None,
    })
    if not pdf:
        return HttpResponse('Error generating PDF', status=500)
    return _pdf(pdf, f'statement_{client.pk}.pdf')


@portal_required
def portal_service_request(request):
    client = _portal_client(request)
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        if message:
            ServiceEnquiry.objects.create(
                name=client.contact_person or client.name,
                email=client.email or (request.user.email or 'portal@sysnet.local'),
                phone=client.phone,
                company=client.name,
                services=['Portal service request'],
                message=message,
            )
            messages.success(request, 'Service request submitted. Our team will contact you.')
            return redirect('portal_dashboard')
    return render(request, 'billing/portal/service_request.html', {'client': client})


@portal_required
def portal_profile(request):
    client = _portal_client(request)
    user = request.user
    if request.method == 'POST':
        # Permitted profile fields only.
        user.first_name = request.POST.get('first_name', user.first_name).strip()[:150]
        user.last_name = request.POST.get('last_name', user.last_name).strip()[:150]
        user.phone = request.POST.get('phone', user.phone).strip()[:32]
        user.save(update_fields=['first_name', 'last_name', 'phone'])
        client.billing_address = request.POST.get('billing_address', client.billing_address).strip()[:2000]
        client.delivery_address = request.POST.get('delivery_address', client.delivery_address).strip()[:2000]
        client.save(update_fields=['billing_address', 'delivery_address'])
        messages.success(request, 'Profile updated.')
        return redirect('portal_profile')
    return render(request, 'billing/portal/profile.html', {'client': client, 'user': user})
