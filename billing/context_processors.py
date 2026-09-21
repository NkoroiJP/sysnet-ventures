from .models import CompanySettings, ServiceEnquiry, ContactMessage, ServicePage


def company_info(request):
    company = CompanySettings.load()
    return {
        'company': company,
        'footer_services': ServicePage.objects.filter(is_active=True).order_by('sort_order')[:6],
        'whatsapp_link': _whatsapp_link(company.whatsapp_number or company.phone),
        'unread_enquiries': (
            ServiceEnquiry.objects.filter(status='new').count() + ContactMessage.objects.filter(is_read=False).count()
        ) if getattr(request, 'user', None) and request.user.is_authenticated else 0,
    }


def _whatsapp_link(number):
    digits = ''.join(ch for ch in number if ch.isdigit())
    if not digits:
        return ''
    if not digits.startswith('254'):
        if digits.startswith('0'):
            digits = '254' + digits[1:]
        elif digits.startswith('7') or digits.startswith('1'):
            digits = '254' + digits
    return f'https://wa.me/{digits}'
