import os
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction, models
from django.db.models import Sum, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import get_template
from django.utils import timezone
from django.views.decorators.http import require_POST

from xhtml2pdf import pisa

from .forms import (
    CustomerForm, QuotationForm, QuotationItemFormSet,
    InvoiceForm, InvoiceItemFormSet, ReceiptForm,
    ProductForm, CompanyProfileForm,
)
from .models import (
    Invoice, InvoiceItem, Quotation, QuotationItem, Receipt, Customer,
    Product, CompanyProfile, ContactMessage, q2,
)

DUE_DAYS_DEFAULT = 30


# ============ helpers ============

def _link_callback(uri, rel):
    """Resolve media URIs to filesystem paths for xhtml2pdf."""
    from django.conf import settings
    media_root = str(settings.MEDIA_ROOT)
    if uri.startswith('/media/'):
        uri = uri[1:]  # strip leading slash -> media/...
    if uri.startswith('media/'):
        candidate = os.path.join(media_root, uri[len('media/'):])
        if os.path.exists(candidate):
            return candidate
    return uri  # remote URLs / data URIs pass through


def render_to_pdf(template_src, context_dict=None):
    context_dict = context_dict or {}
    template = get_template(template_src)
    html = template.render(context_dict)
    response = HttpResponse(content_type='application/pdf')
    pisa_status = pisa.CreatePDF(html, dest=response, link_callback=_link_callback)
    if pisa_status.err:
        return None
    return response


def _pdf_response(pdf, filename):
    response = HttpResponse(pdf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


# ============ dashboard ============

@login_required
def dashboard(request):
    receipts_total = Receipt.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    month_start = timezone.localdate().replace(day=1)
    month_revenue = Receipt.objects.filter(date__gte=month_start).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    unpaid = [inv for inv in Invoice.objects.exclude(status=Invoice.PAID)]
    outstanding = sum((inv.balance_due for inv in unpaid), Decimal('0'))
    overdue_count = sum(1 for inv in unpaid if inv.effective_status == Invoice.OVERDUE)

    context = {
        'total_revenue': q2(receipts_total),
        'month_revenue': q2(month_revenue),
        'outstanding': q2(outstanding),
        'overdue_count': overdue_count,
        'pending_invoices_amount': q2(outstanding),
        'pending_invoices_count': len(unpaid),
        'total_customers': Customer.objects.count(),
        'active_quotes': Quotation.objects.filter(status=Quotation.SENT).count(),
        'recent_invoices': Invoice.objects.select_related('customer').order_by('-created_at')[:6],
        'recent_receipts': Receipt.objects.select_related('invoice', 'invoice__customer').order_by('-date', '-id')[:5],
        'expiring_quotes': (
            Quotation.objects.filter(status=Quotation.SENT, valid_until__gte=timezone.localdate())
            .order_by('valid_until')[:5]
        ),
        'top_customers': (
            Customer.objects.annotate(revenue=Sum('invoices__receipts__amount'))
            .filter(revenue__gt=0).order_by('-revenue')[:5]
        ),
        'company': CompanyProfile.load(),
        'today': timezone.localdate(),
    }
    return render(request, 'billing/dashboard.html', context)


# ============ customers ============

@login_required
def customer_list(request):
    qs = Customer.objects.prefetch_related('invoices')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q))

    for c in qs:
        c.invoice_count = c.invoices.count()
        c.total_billed_sum = q2(sum((i.total_amount for i in c.invoices.all()), Decimal('0')))
        c.outstanding = q2(sum((i.balance_due for i in c.invoices.exclude(status=Invoice.PAID)), Decimal('0')))

    return render(request, 'billing/customer_list.html', {'customers': list(qs), 'search_query': q})


@login_required
def customer_create(request):
    next_url = request.GET.get('next')
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            messages.success(request, f'Customer {customer.name} added.')
            if next_url:
                return redirect(next_url)
            return redirect('customer_list')
    else:
        form = CustomerForm()
    return render(request, 'billing/customer_form.html', {'form': form, 'title': 'Add Customer', 'next': next_url})


@login_required
def customer_create_modal(request):
    """AJAX: create a customer inline from the quotation/invoice form."""
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            return JsonResponse({'success': True, 'id': customer.id, 'name': customer.name})
        errors = {f: [str(e) for e in errs] for f, errs in form.errors.items()}
        return JsonResponse({'success': False, 'errors': errors}, status=400)
    return JsonResponse({'success': False}, status=405)


@login_required
def customer_update(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer updated.')
            return redirect('customer_list')
    else:
        form = CustomerForm(instance=customer)
    return render(request, 'billing/customer_form.html', {'form': form, 'title': 'Edit Customer'})


@login_required
@require_POST
def customer_delete(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if customer.invoices.exists() or customer.quotations.exists():
        messages.error(request, f'{customer.name} has invoices or quotations and cannot be deleted.')
    else:
        customer.delete()
        messages.success(request, 'Customer deleted.')
    return redirect('customer_list')


# ============ quotations ============

@login_required
def quotation_list(request):
    qs = Quotation.objects.select_related('customer').order_by('-date', '-id')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(customer__name__icontains=q))
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'billing/quotation_list.html', {
        'quotes': page.object_list, 'page_obj': page,
        'search_query': q, 'status_filter': status,
        'status_choices': Quotation.STATUS_CHOICES,
        'today': timezone.localdate(),
    })


@login_required
def quotation_create(request):
    if request.method == 'POST':
        form = QuotationForm(request.POST)
        formset = QuotationItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                quotation = form.save()
                formset.instance = quotation
                formset.save()
            messages.success(request, f'Quotation {quotation.number} created.')
            if request.POST.get('save_and') == 'invoice':
                return redirect('convert_quote_to_invoice', pk=quotation.pk)
            return redirect('quotation_detail', pk=quotation.pk)
    else:
        form = QuotationForm()
        formset = QuotationItemFormSet()
    return render(request, 'billing/quotation_form.html', {'form': form, 'formset': formset, 'title': 'Create Quotation'})


@login_required
def quotation_update(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if request.method == 'POST':
        form = QuotationForm(request.POST, instance=quotation)
        formset = QuotationItemFormSet(request.POST, instance=quotation)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, f'Quotation {quotation.number} updated.')
            return redirect('quotation_detail', pk=quotation.pk)
    else:
        form = QuotationForm(instance=quotation)
        formset = QuotationItemFormSet(instance=quotation)
    return render(request, 'billing/quotation_form.html', {'form': form, 'formset': formset, 'title': 'Edit Quotation'})


@login_required
def quotation_detail(request, pk):
    quotation = get_object_or_404(Quotation.objects.select_related('customer'), pk=pk)
    return render(request, 'billing/quotation_detail.html', {
        'quotation': quotation,
        'company': CompanyProfile.load(),
    })


@login_required
@require_POST
def convert_quote_to_invoice(request, pk):
    quote = get_object_or_404(Quotation, pk=pk)
    if quote.is_converted:
        messages.info(request, f'Quotation {quote.number} was already converted (Invoice {quote.invoice.number}).')
        return redirect('invoice_detail', pk=quote.invoice.pk)
    if quote.status not in (Quotation.SENT, Quotation.ACCEPTED):
        messages.warning(request, 'Mark the quotation as Sent or Accepted before converting it to an invoice.')
        return redirect('quotation_detail', pk=quote.pk)

    with transaction.atomic():
        invoice = Invoice.objects.create(
            customer=quote.customer,
            quotation=quote,
            date=timezone.localdate(),
            due_date=timezone.localdate() + timezone.timedelta(days=DUE_DAYS_DEFAULT),
            tax_rate=quote.tax_rate,
            notes=quote.notes,
            status=Invoice.PENDING,
        )
        for item in quote.items.all():
            InvoiceItem.objects.create(
                invoice=invoice,
                product=item.product,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
            )
        quote.status = Quotation.ACCEPTED
        quote.save(update_fields=['status'])

    messages.success(request, f'Quotation {quote.number} converted to Invoice {invoice.number}.')
    return redirect('invoice_detail', pk=invoice.pk)


@login_required
@require_POST
def quotation_set_status(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    status = request.POST.get('status')
    if status not in dict(Quotation.STATUS_CHOICES):
        messages.error(request, 'Invalid status.')
        return redirect('quotation_detail', pk=quotation.pk)
    if quotation.is_converted and status != Quotation.ACCEPTED:
        messages.warning(request, 'This quotation was converted to an invoice; its status stays Accepted.')
        return redirect('quotation_detail', pk=quotation.pk)
    quotation.status = status
    quotation.save(update_fields=['status'])
    messages.success(request, f'Quotation {quotation.number} marked as {quotation.get_status_display()}.')
    return redirect('quotation_detail', pk=quotation.pk)


@login_required
@require_POST
def quotation_delete(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.is_converted:
        messages.error(request, 'Cannot delete a quotation that has been converted to an invoice.')
    else:
        quotation.delete()
        messages.success(request, 'Quotation deleted.')
    return redirect('quotation_list')


# ============ invoices ============

@login_required
def invoice_list(request):
    qs = Invoice.objects.select_related('customer').order_by('-date', '-id')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(customer__name__icontains=q))
    if status == Invoice.OVERDUE:
        qs = qs.exclude(status=Invoice.PAID).filter(due_date__lt=timezone.localdate())
    elif status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'billing/invoice_list.html', {
        'invoices': page.object_list, 'page_obj': page,
        'search_query': q, 'status_filter': status,
        'status_choices': Invoice.STATUS_CHOICES,
    })


@login_required
def invoice_create(request):
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                invoice = form.save()
                formset.instance = invoice
                formset.save()
            messages.success(request, f'Invoice {invoice.number} created.')
            return redirect('invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm()
        formset = InvoiceItemFormSet()
    return render(request, 'billing/invoice_form.html', {'form': form, 'formset': formset, 'title': 'Create Invoice'})


@login_required
def invoice_update(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice)
        formset = InvoiceItemFormSet(request.POST, instance=invoice)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            invoice.refresh_from_db()
            invoice.mark_paid_if_settled()
            return redirect('invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm(instance=invoice)
        formset = InvoiceItemFormSet(instance=invoice)
    return render(request, 'billing/invoice_form.html', {'form': form, 'formset': formset, 'title': 'Edit Invoice'})


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related('customer'), pk=pk)
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'company': CompanyProfile.load(),
        'receipts': invoice.receipts.order_by('-date', '-id'),
    })


@login_required
def add_receipt(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    if invoice.status == Invoice.PAID:
        messages.info(request, f'Invoice {invoice.number} is already fully paid.')
        return redirect('invoice_detail', pk=invoice.pk)
    if request.method == 'POST':
        form = ReceiptForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                receipt = form.save(commit=False)
                receipt.invoice = invoice
                receipt.save()
                invoice.mark_paid_if_settled()
            messages.success(request, f'Payment of {CompanyProfile.load().currency} {receipt.amount} recorded on {invoice.number}.')
            return redirect('receipt_detail', pk=receipt.pk)
    else:
        form = ReceiptForm(invoice=invoice)
    return render(request, 'billing/receipt_form.html', {'form': form, 'invoice': invoice})


@login_required
@require_POST
def receipt_delete(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    invoice_pk = receipt.invoice_id
    receipt_number = receipt.number
    receipt.delete()  # model.delete() restores invoice status if it was marked paid
    messages.success(request, f'Payment {receipt_number} deleted; invoice status updated.')
    return redirect('invoice_detail', pk=invoice_pk)


# ============ receipts ============

@login_required
def receipt_list(request):
    receipts = Receipt.objects.select_related('invoice', 'invoice__customer').order_by('-date', '-id')
    q = request.GET.get('q', '').strip()
    if q:
        receipts = receipts.filter(
            Q(number__icontains=q) | Q(invoice__number__icontains=q) | Q(invoice__customer__name__icontains=q)
        )
    paginator = Paginator(receipts, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'billing/receipt_list.html', {
        'receipts': page.object_list, 'page_obj': page, 'search_query': q,
    })


@login_required
def receipt_detail(request, pk):
    receipt = get_object_or_404(Receipt.objects.select_related('invoice', 'invoice__customer'), pk=pk)
    return render(request, 'billing/receipt_detail.html', {'receipt': receipt, 'company': CompanyProfile.load()})


# ============ products ============

@login_required
def product_list(request):
    products = Product.objects.all().order_by('name')
    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(description__icontains=q))
    return render(request, 'billing/product_list.html', {'products': products, 'search_query': q})


@login_required
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product added.')
            return redirect('product_list')
    else:
        form = ProductForm()
    return render(request, 'billing/product_form.html', {'form': form, 'title': 'Add Product'})


@login_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated.')
            return redirect('product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'billing/product_form.html', {'form': form, 'title': 'Edit Product'})


@login_required
@require_POST
def product_delete(request, pk):
    """Archive instead of hard delete so historical documents keep their data."""
    product = get_object_or_404(Product, pk=pk)
    product.is_active = False
    product.save(update_fields=['is_active'])
    messages.success(request, f'{product.name} archived. It will no longer appear in new document lines.')
    return redirect('product_list')


# ============ messages / contact form ============

@login_required
def message_list(request):
    unread_count = ContactMessage.objects.filter(is_read=False).count()
    messages_qs = ContactMessage.objects.all()
    return render(request, 'billing/message_list.html', {
        'messages': messages_qs,
        'unread_count': unread_count,
    })


@login_required
def message_detail(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    if not message.is_read:
        message.is_read = True
        message.save(update_fields=['is_read'])
    return render(request, 'billing/message_detail.html', {'message': message})


@require_POST
@login_required
def message_mark_read(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    message.is_read = True
    message.save(update_fields=['is_read'])
    return JsonResponse({'success': True, 'is_read': True})


@require_POST
@login_required
def message_mark_unread(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    message.is_read = False
    message.save(update_fields=['is_read'])
    return JsonResponse({'success': True, 'is_read': False})


@require_POST
@login_required
def message_delete(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    message.delete()
    messages.success(request, 'Message deleted successfully')
    return redirect('message_list')


# ============ settings ============

@login_required
def company_settings(request):
    company = CompanyProfile.load()
    if request.method == 'POST':
        form = CompanyProfileForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, 'Company settings saved.')
            return redirect('company_settings')
    else:
        form = CompanyProfileForm(instance=company)
    return render(request, 'billing/company_settings.html', {'form': form})


# ============ PDF generation ============

@login_required
def quotation_pdf(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    pdf = render_to_pdf('billing/pdf_quotation.html', {'quotation': quotation, 'company': CompanyProfile.load()})
    if pdf:
        return _pdf_response(pdf, f"{quotation.number.replace('-', '_')}.pdf")
    return HttpResponse("Error generating PDF", status=500)


@login_required
def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    pdf = render_to_pdf('billing/pdf_invoice.html', {'invoice': invoice, 'company': CompanyProfile.load()})
    if pdf:
        return _pdf_response(pdf, f"{invoice.number.replace('-', '_')}.pdf")
    return HttpResponse("Error generating PDF", status=500)


@login_required
def receipt_pdf(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    pdf = render_to_pdf('billing/pdf_receipt.html', {'receipt': receipt, 'company': CompanyProfile.load()})
    if pdf:
        return _pdf_response(pdf, f"{receipt.number.replace('-', '_')}.pdf")
    return HttpResponse("Error generating PDF", status=500)


# ============ ajax / api ============

@login_required
def product_api(request, pk):
    """API endpoint to get product data for AJAX auto-fill."""
    product = get_object_or_404(Product, pk=pk)
    return JsonResponse({
        'id': product.id,
        'name': product.name,
        'price': str(product.price),
        'description': product.description or '',
        'product_type': product.product_type,
    })
