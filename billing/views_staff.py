"""Staff-side views: dashboard, clients, catalog, enquiries, settings."""
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, Q, Count
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.audit import audit
from accounts.models import User
from .access import staff_required, superadmin_required
from .forms import (
    ClientForm, ProductForm, CompanySettingsForm, TaxCategoryForm,
    ServiceEnquiryForm,
)
from .models import (
    CompanySettings, TaxCategory, Client, Product, Quotation, Invoice,
    Payment, PaymentSubmission, Receipt, ServiceEnquiry, ContactMessage,
    NotificationLog,
)
from .money import q2


# ==================================================================== dashboard

@staff_required
def dashboard(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)

    revenue = q2(Receipt.objects.aggregate(t=Sum('amount'))['t'] or 0)
    month_revenue = q2(Receipt.objects.filter(payment__paid_on__gte=month_start).aggregate(t=Sum('amount'))['t'] or 0)
    invoiced_total = q2(sum((i.total for i in Invoice.objects.exclude(status=Invoice.VOIDED)), Decimal('0')))
    outstanding = q2(sum((i.balance_due for i in Invoice.objects.exclude(status__in=[Invoice.VOIDED, Invoice.DRAFT])), Decimal('0')))
    overdue_invoices = [i for i in Invoice.objects.exclude(status__in=[Invoice.VOIDED, Invoice.DRAFT, Invoice.PAID])
                        if i.effective_status == Invoice.OVERDUE]
    overdue_amount = q2(sum((i.balance_due for i in overdue_invoices), Decimal('0')))

    pending_quotes = Quotation.objects.filter(status__in=[Quotation.SENT, Quotation.VIEWED]).count()
    accepted_quotes = Quotation.objects.filter(status=Quotation.ACCEPTED).count()
    pending_verifications = PaymentSubmission.objects.filter(status=Payment.PENDING).count()
    unallocated_total = q2(sum((p.unallocated for p in Payment.objects.filter(status=Payment.CONFIRMED)), Decimal('0')))

    # monthly revenue chart (last 12 months)
    months = []
    for i in range(11, -1, -1):
        m = (month_start.month - i - 1) % 12 + 1
        y = month_start.year + (month_start.month - i - 1) // 12
        start = timezone.datetime(y, m, 1).date()
        if m == 12:
            end = timezone.datetime(y + 1, 1, 1).date()
        else:
            end = timezone.datetime(y, m + 1, 1).date()
        total = Receipt.objects.filter(payment__paid_on__gte=start, payment__paid_on__lt=end).aggregate(t=Sum('amount'))['t'] or 0
        months.append({'label': start.strftime('%b %y'), 'total': q2(total)})
    max_month = max((m['total'] for m in months), default=Decimal('0'))

    # aging buckets
    aging = {'current': Decimal('0'), 'd30': Decimal('0'), 'd60': Decimal('0'), 'd90': Decimal('0'), 'd90p': Decimal('0')}
    for inv in Invoice.objects.exclude(status__in=[Invoice.VOIDED, Invoice.DRAFT, Invoice.PAID]):
        if inv.due_date and inv.due_date < today:
            days = (today - inv.due_date).days
            if days <= 30:
                aging['d30'] += inv.balance_due
            elif days <= 60:
                aging['d60'] += inv.balance_due
            elif days <= 90:
                aging['d90'] += inv.balance_due
            else:
                aging['d90p'] += inv.balance_due
        else:
            aging['current'] += inv.balance_due
    aging = {k: q2(v) for k, v in aging.items()}

    context = {
        'revenue': revenue,
        'month_revenue': month_revenue,
        'invoiced_total': invoiced_total,
        'outstanding': outstanding,
        'overdue_count': len(overdue_invoices),
        'overdue_amount': overdue_amount,
        'overdue_invoices': overdue_invoices[:6],
        'pending_quotes': pending_quotes,
        'accepted_quotes': accepted_quotes,
        'pending_verifications': pending_verifications,
        'unallocated_total': unallocated_total,
        'recent_payments': Payment.objects.select_related('client').order_by('-created_at')[:8],
        'recent_clients': Client.objects.order_by('-created_at')[:5],
        'months': months,
        'max_month': max_month,
        'aging': aging,
        'today': today,
    }
    return render(request, 'billing/dashboard.html', context)


# ==================================================================== clients

@staff_required
def client_list(request):
    qs = Client.objects.all()
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q) | Q(contact_person__icontains=q))
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs.order_by('name'), 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'billing/client_list.html', {
        'clients': page.object_list, 'page_obj': page,
        'search_query': q, 'status_filter': status,
        'status_choices': Client.STATUS_CHOICES,
    })


@staff_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    return render(request, 'billing/client_detail.html', {
        'client': client,
        'invoices': client.invoices.order_by('-issue_date')[:10],
        'quotations': client.quotations.order_by('-issue_date')[:10],
        'payments': client.payments.order_by('-paid_on')[:10],
        'receipts': client.receipts.order_by('-issued_at')[:10],
        'contacts': client.contacts.all(),
        'statement_entries': None,
    })


@staff_required
def client_create(request):
    next_url = request.GET.get('next') or request.POST.get('next')
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.created_by = request.user
            client.save()
            audit('create', client, user=request.user)
            messages.success(request, f'Client {client.name} created.')
            return redirect(next_url or 'client_detail', pk=client.pk)
    else:
        form = ClientForm()
    return render(request, 'billing/client_form.html', {'form': form, 'title': 'Add Client', 'next': next_url})


@staff_required
def client_update(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            audit('update', client, user=request.user)
            messages.success(request, 'Client updated.')
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm(instance=client)
    return render(request, 'billing/client_form.html', {'form': form, 'title': f'Edit — {client.name}'})


@staff_required
@require_POST
def client_archive(request, pk):
    client = get_object_or_404(Client, pk=pk)
    client.status = Client.INACTIVE
    client.save(update_fields=['status'])
    audit('status', client, detail='archived', user=request.user)
    messages.success(request, f'{client.name} marked inactive.')
    return redirect('client_list')


# ==================================================================== catalog

@staff_required
def product_list(request):
    qs = Product.objects.all()
    q = request.GET.get('q', '').strip()
    show_archived = request.GET.get('archived') == '1'
    if not show_archived:
        qs = qs.filter(is_active=True)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(category__icontains=q))
    paginator = Paginator(qs.order_by('name'), 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'billing/product_list.html', {
        'products': page.object_list, 'page_obj': page,
        'search_query': q, 'show_archived': show_archived,
    })


@staff_required
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save()
            audit('create', product, user=request.user)
            messages.success(request, f'{product.name} added to catalog.')
            return redirect('product_list')
    else:
        form = ProductForm()
    return render(request, 'billing/product_form.html', {'form': form, 'title': 'Add catalog item'})


@staff_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            audit('update', product, user=request.user)
            messages.success(request, f'{product.name} updated.')
            return redirect('product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'billing/product_form.html', {'form': form, 'title': f'Edit — {product.name}'})


@staff_required
@require_POST
def product_archive(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.is_active = not product.is_active
    product.save(update_fields=['is_active'])
    audit('status', product, user=request.user, detail='archived' if not product.is_active else 'reactivated')
    state = 'archived' if not product.is_active else 'reactivated'
    messages.success(request, f'{product.name} {state}.')
    return redirect('product_list')


# ==================================================================== enquiries

@staff_required
def enquiry_list(request):
    enquiries = ServiceEnquiry.objects.all()
    messages_qs = ContactMessage.objects.all()
    status = request.GET.get('status', '').strip()
    if status:
        enquiries = enquiries.filter(status=status)
    return render(request, 'billing/enquiry_list.html', {
        'enquiries': enquiries,
        'messages': messages_qs,
        'status_filter': status,
        'status_choices': ServiceEnquiry.STATUS_CHOICES,
    })


@staff_required
@require_POST
def enquiry_set_status(request, pk):
    enquiry = get_object_or_404(ServiceEnquiry, pk=pk)
    status = request.POST.get('status')
    if status in dict(ServiceEnquiry.STATUS_CHOICES):
        enquiry.status = status
        enquiry.save(update_fields=['status'])
        messages.success(request, f'Enquiry marked {enquiry.get_status_display()}.')
    return redirect('enquiry_list')


@staff_required
@require_POST
def message_mark_read(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    msg.is_read = not msg.is_read
    msg.save(update_fields=['is_read'])
    return redirect('enquiry_list')


@staff_required
@require_POST
def message_delete(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    msg.delete()
    messages.success(request, 'Message deleted.')
    return redirect('enquiry_list')


# ==================================================================== settings

@superadmin_required
def company_settings(request):
    company = CompanySettings.load()
    if request.method == 'POST':
        form = CompanySettingsForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            audit('admin', company, user=request.user, detail='settings updated')
            messages.success(request, 'Company settings saved.')
            return redirect('company_settings')
    else:
        form = CompanySettingsForm(instance=company)
    return render(request, 'billing/company_settings.html', {'form': form})


@superadmin_required
def tax_categories(request):
    cats = TaxCategory.objects.all()
    if request.method == 'POST':
        form = TaxCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tax category added.')
            return redirect('tax_categories')
    else:
        form = TaxCategoryForm()
    return render(request, 'billing/tax_categories.html', {'categories': cats, 'form': form})


@superadmin_required
def tax_category_update(request, pk):
    cat = get_object_or_404(TaxCategory, pk=pk)
    if request.method == 'POST':
        form = TaxCategoryForm(request.POST, instance=cat)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tax category updated.')
            return redirect('tax_categories')
    else:
        form = TaxCategoryForm(instance=cat)
    return render(request, 'billing/tax_category_form.html', {'form': form, 'title': f'Edit — {cat.name}'})


@superadmin_required
def user_list(request):
    users = User.objects.all().order_by('username')
    return render(request, 'billing/user_list.html', {'users': users})


@superadmin_required
def user_create(request):
    from accounts.forms import UserForm
    form = UserForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        audit('admin', user, user=request.user, detail=f'user {user.username} created')
        messages.success(request, f'User {user.username} created.')
        return redirect('user_list')
    return render(request, 'billing/user_form.html', {'form': form, 'title': 'Add user'})


@superadmin_required
def user_update(request, pk):
    from accounts.forms import UserForm
    user_obj = get_object_or_404(User, pk=pk)
    form = UserForm(request.POST or None, instance=user_obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        audit('admin', user_obj, user=request.user, detail=f'user {user_obj.username} updated')
        messages.success(request, f'User {user_obj.username} updated.')
        return redirect('user_list')
    return render(request, 'billing/user_form.html', {'form': form, 'title': f'Edit user — {user_obj.username}'})


@superadmin_required
@require_POST
def user_toggle_active(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    if user_obj.pk == request.user.pk:
        messages.error(request, 'You cannot deactivate your own account.')
    else:
        user_obj.is_active = not user_obj.is_active
        user_obj.save(update_fields=['is_active'])
        audit('admin', user_obj, user=request.user, detail='activated' if user_obj.is_active else 'deactivated')
        messages.success(request, f'{user_obj.username} {"activated" if user_obj.is_active else "deactivated"}.')
    return redirect('user_list')


@superadmin_required
def audit_log(request):
    from accounts.models import AuditLog
    entries = AuditLog.objects.select_related('user').all()[:200]
    return render(request, 'billing/audit_log.html', {'entries': entries})
