"""Public corporate website views."""
from django.conf import settings as dj_settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.throttle import client_ip
from billing.emails import notify_contact_message, notify_new_enquiry
from billing.forms import ContactForm, ServiceEnquiryForm
from billing.models import (
    CompanySettings, ServicePage, Product, Project, Testimonial,
    ServiceEnquiry, ContactMessage,
)


def _rate_limited(request, scope, limit=None, window=3600):
    """Cheap cache-based rate limiting for public forms."""
    ip = client_ip(request)
    key = f'rl:{scope}:{ip}'
    count = cache.get(key, 0)
    max_hits = limit or dj_settings.THROTTLE_CONFIG['public_form']['limit']
    if count >= max_hits:
        return True
    cache.set(key, count + 1, window)
    return False


def home(request):
    return render(request, 'website/home.html', {
        'services': ServicePage.objects.filter(is_active=True)[:8],
        'projects': Project.objects.filter(is_public=True)[:3],
        'meta_title': 'Sysnet Technologies — ICT Solutions, Networking & IT Services in Kenya',
        'meta_description': 'Sysnet Technologies delivers enterprise networking, fiber and GPON solutions, '
                            'software development, cloud, cybersecurity and managed IT services across Kenya.',
    })


def about(request):
    return render(request, 'website/about.html', {
        'meta_title': 'About Sysnet Technologies — ICT Partner in Kenya',
        'meta_description': 'Sysnet Technologies is a Kenyan ICT company providing networking, fiber/GPON, '
                            'software development, cloud, cybersecurity and managed IT services.',
    })


def service_list(request):
    return render(request, 'website/service_list.html', {
        'services': ServicePage.objects.filter(is_active=True),
        'meta_title': 'ICT Services — Sysnet Technologies',
        'meta_description': 'Enterprise networking, fiber & GPON, computer sales & maintenance, software '
                            'development, cloud, cybersecurity, managed IT and automation services.',
    })


def service_detail(request, slug):
    service = get_object_or_404(ServicePage, slug=slug, is_active=True)
    return render(request, 'website/service_detail.html', {
        'service': service,
        'enquiry_form': ServiceEnquiryForm(initial={'services': service.title}),
        'other_services': ServicePage.objects.filter(is_active=True).exclude(pk=service.pk)[:4],
        'meta_title': service.meta_title or f'{service.title} — Sysnet Technologies',
        'meta_description': service.meta_description or service.summary,
    })


def product_catalog(request):
    products = Product.objects.filter(is_active=True, public_show=True)
    category = request.GET.get('category', '').strip()
    if category:
        products = products.filter(category__iexact=category)
    categories = (Product.objects.filter(is_active=True, public_show=True)
                  .exclude(category='').values_list('category', flat=True).distinct())
    return render(request, 'website/product_catalog.html', {
        'products': products,
        'categories': categories,
        'active_category': category,
        'meta_title': 'Products & IT Solutions — Sysnet Technologies',
        'meta_description': 'Computers, accessories and technology solutions from Sysnet Technologies. '
                            'Enquire for pricing and availability.',
    })


def portfolio(request):
    return render(request, 'website/portfolio.html', {
        'projects': Project.objects.filter(is_public=True),
        'meta_title': 'Projects & Portfolio — Sysnet Technologies',
        'meta_description': 'Selected projects delivered by Sysnet Technologies across Kenya.',
    })


def contact(request):
    if request.method == 'POST':
        if _rate_limited(request, 'contact'):
            return render(request, 'website/contact.html', {
                'form': ContactForm(),
                'rate_limited': True,
            }, status=429)
        form = ContactForm(request.POST)
        if form.is_valid():
            msg = form.save()
            notify_contact_message(msg)
            return render(request, 'website/contact.html', {'form': ContactForm(), 'sent': True})
    else:
        form = ContactForm()
    return render(request, 'website/contact.html', {
        'form': form,
        'meta_title': 'Contact Sysnet Technologies — +254710779799',
        'meta_description': 'Contact Sysnet Technologies for ICT solutions in Kenya. Call +254710779799, '
                            'WhatsApp us or send a message.',
    })


def request_quote(request):
    if request.method == 'POST':
        if _rate_limited(request, 'quote'):
            return render(request, 'website/request_quote.html', {
                'form': ServiceEnquiryForm(),
                'services': ServicePage.objects.filter(is_active=True),
                'rate_limited': True,
            }, status=429)
        form = ServiceEnquiryForm(request.POST)
        if form.is_valid():
            enquiry = form.save()
            notify_new_enquiry(enquiry)
            return render(request, 'website/request_quote.html', {
                'form': ServiceEnquiryForm(),
                'services': ServicePage.objects.filter(is_active=True),
                'sent': True,
            })
    else:
        initial = {}
        pre = request.GET.get('service')
        if pre:
            initial['services'] = pre
        form = ServiceEnquiryForm(initial=initial)
    return render(request, 'website/request_quote.html', {
        'form': form,
        'services': ServicePage.objects.filter(is_active=True),
        'meta_title': 'Request a Quote — Sysnet Technologies',
        'meta_description': 'Request a quotation for ICT services and solutions from Sysnet Technologies.',
    })
