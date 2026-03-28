from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db import transaction
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import Invoice, Quotation, Receipt, Customer, InvoiceItem, QuotationItem, Product, CompanyProfile, ContactMessage
from .forms import (
    CustomerForm, QuotationForm, QuotationItemFormSet,
    InvoiceForm, InvoiceItemFormSet, ReceiptForm,
    ProductForm, CompanyProfileForm
)

# --- Dashboard ---
@login_required
def dashboard(request):
    total_revenue = Receipt.objects.aggregate(total=Sum('amount'))['total'] or 0
    
    pending_invoices_amount = 0
    pending_invoices = Invoice.objects.filter(status__in=[Invoice.PENDING, Invoice.OVERDUE])
    for inv in pending_invoices:
        pending_invoices_amount += inv.balance_due

    total_customers = Customer.objects.count()
    active_quotes = Quotation.objects.filter(status=Quotation.SENT).count()

    recent_invoices = Invoice.objects.select_related('customer').order_by('-created_at')[:5]

    context = {
        'total_revenue': total_revenue,
        'pending_invoices_amount': pending_invoices_amount,
        'total_customers': total_customers,
        'active_quotes': active_quotes,
        'recent_invoices': recent_invoices,
    }
    return render(request, 'billing/dashboard.html', context)

# --- Customers ---
@login_required
def customer_list(request):
    customers = Customer.objects.all().order_by('-created_at')
    return render(request, 'billing/customer_list.html', {'customers': customers})

@login_required
def customer_create(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('customer_list')
    else:
        form = CustomerForm()
    return render(request, 'billing/customer_form.html', {'form': form, 'title': 'Add Customer'})

@login_required
def customer_update(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            return redirect('customer_list')
    else:
        form = CustomerForm(instance=customer)
    return render(request, 'billing/customer_form.html', {'form': form, 'title': 'Edit Customer'})

# --- Quotations ---
@login_required
def quotation_list(request):
    quotations = Quotation.objects.select_related('customer').order_by('-created_at')
    return render(request, 'billing/quotation_list.html', {'quotations': quotations})

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
            return redirect('quotation_detail', pk=quotation.pk)
    else:
        form = QuotationForm(instance=quotation)
        formset = QuotationItemFormSet(instance=quotation)
    return render(request, 'billing/quotation_form.html', {'form': form, 'formset': formset, 'title': 'Edit Quotation'})

@login_required
def quotation_detail(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    company = CompanyProfile.objects.first()
    return render(request, 'billing/quotation_detail.html', {'quotation': quotation, 'company': company})

@login_required
def convert_quote_to_invoice(request, pk):
    quote = get_object_or_404(Quotation, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            invoice = Invoice.objects.create(
                customer=quote.customer,
                quotation=quote,
                date=quote.date,
                status=Invoice.PENDING
            )
            for item in quote.items.all():
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=item.product,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price
                )
            # Update quote status
            quote.status = Quotation.ACCEPTED
            quote.save()
            return redirect('invoice_detail', pk=invoice.pk)
    return redirect('quotation_detail', pk=pk)

# --- Invoices ---
@login_required
def invoice_list(request):
    invoices = Invoice.objects.select_related('customer').order_by('-created_at')
    return render(request, 'billing/invoice_list.html', {'invoices': invoices})

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
            return redirect('invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm(instance=invoice)
        formset = InvoiceItemFormSet(instance=invoice)
    return render(request, 'billing/invoice_form.html', {'form': form, 'formset': formset, 'title': 'Edit Invoice'})

@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    company = CompanyProfile.objects.first()
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice, 'company': company})

@login_required
def add_receipt(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    if request.method == 'POST':
        form = ReceiptForm(request.POST)
        if form.is_valid():
            receipt = form.save(commit=False)
            receipt.invoice = invoice
            receipt.save()
            
            # Check if fully paid
            if invoice.balance_due <= 0:
                invoice.status = Invoice.PAID
                invoice.save()
                
            return redirect('invoice_detail', pk=invoice.pk)
    else:
        # Pre-fill amount with balance due
        form = ReceiptForm(initial={'amount': invoice.balance_due})
    
    return render(request, 'billing/receipt_form.html', {'form': form, 'invoice': invoice})

# --- Receipts ---
@login_required
def receipt_list(request):
    receipts = Receipt.objects.select_related('invoice', 'invoice__customer').order_by('-date')
    return render(request, 'billing/receipt_list.html', {'receipts': receipts})

@login_required
def receipt_detail(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    company = CompanyProfile.objects.first()
    return render(request, 'billing/receipt_detail.html', {'receipt': receipt, 'company': company})

# --- Products ---
@login_required
def product_list(request):
    products = Product.objects.all().order_by('name')
    return render(request, 'billing/product_list.html', {'products': products})

@login_required
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
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
            return redirect('product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'billing/product_form.html', {'form': form, 'title': 'Edit Product'})

def product_api(request, pk):
    """API endpoint to get product data for AJAX calls"""
    product = get_object_or_404(Product, pk=pk)
    return JsonResponse({
        'id': product.id,
        'name': product.name,
        'price': str(product.price),
        'description': product.description or '',
        'product_type': product.product_type
    })

# --- Messages / Contact Form ---
@login_required
def message_list(request):
    """List all contact messages"""
    unread_count = ContactMessage.objects.filter(is_read=False).count()
    messages_qs = ContactMessage.objects.all()
    return render(request, 'billing/message_list.html', {
        'messages': messages_qs,
        'unread_count': unread_count
    })

@login_required
def message_detail(request, pk):
    """View a single message and mark as read"""
    message = get_object_or_404(ContactMessage, pk=pk)
    if not message.is_read:
        message.is_read = True
        message.save()
    return render(request, 'billing/message_detail.html', {'message': message})

@require_POST
@login_required
def message_mark_read(request, pk):
    """Mark a message as read via AJAX"""
    message = get_object_or_404(ContactMessage, pk=pk)
    message.is_read = True
    message.save()
    return JsonResponse({'success': True, 'is_read': True})

@require_POST
@login_required
def message_mark_unread(request, pk):
    """Mark a message as unread via AJAX"""
    message = get_object_or_404(ContactMessage, pk=pk)
    message.is_read = False
    message.save()
    return JsonResponse({'success': True, 'is_read': False})

@require_POST
@login_required
def message_delete(request, pk):
    """Delete a message"""
    message = get_object_or_404(ContactMessage, pk=pk)
    message.delete()
    messages.success(request, 'Message deleted successfully')
    return redirect('message_list')

# --- Settings ---
@login_required
def company_settings(request):
    company = CompanyProfile.objects.first()
    if request.method == 'POST':
        form = CompanyProfileForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = CompanyProfileForm(instance=company)
    return render(request, 'billing/company_settings.html', {'form': form})

# --- PDF Generation ---
def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    response = HttpResponse(content_type='application/pdf')
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return None
    return response

@login_required
def quotation_pdf(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    company = CompanyProfile.objects.first()
    data = {'quotation': quotation, 'company': company}
    pdf = render_to_pdf('billing/pdf_quotation.html', data)
    if pdf:
        response = HttpResponse(pdf.getvalue(), content_type='application/pdf')
        filename = f"Quotation_{quotation.id}.pdf"
        content = f"inline; filename={filename}"
        response['Content-Disposition'] = content
        return response
    return HttpResponse("Error generating PDF", status=500)

@login_required
def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    company = CompanyProfile.objects.first()
    data = {'invoice': invoice, 'company': company}
    pdf = render_to_pdf('billing/pdf_invoice.html', data)
    if pdf:
        response = HttpResponse(pdf.getvalue(), content_type='application/pdf')
        filename = f"Invoice_{invoice.id}.pdf"
        content = f"inline; filename={filename}"
        response['Content-Disposition'] = content
        return response
    return HttpResponse("Error generating PDF", status=500)

@login_required
def receipt_pdf(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    company = CompanyProfile.objects.first()
    data = {'receipt': receipt, 'company': company}
    pdf = render_to_pdf('billing/pdf_receipt.html', data)
    if pdf:
        response = HttpResponse(pdf.getvalue(), content_type='application/pdf')
        filename = f"Receipt_{receipt.id}.pdf"
        content = f"inline; filename={filename}"
        response['Content-Disposition'] = content
        return response
    return HttpResponse("Error generating PDF", status=500)
