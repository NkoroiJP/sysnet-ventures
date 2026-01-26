from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db import transaction
from django.urls import reverse
from .models import Invoice, Quotation, Receipt, Customer, InvoiceItem, QuotationItem
from .forms import (
    CustomerForm, QuotationForm, QuotationItemFormSet, 
    InvoiceForm, InvoiceItemFormSet, ReceiptForm
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
    return render(request, 'billing/quotation_detail.html', {'quotation': quotation})

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
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice})

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
    return render(request, 'billing/receipt_detail.html', {'receipt': receipt})
