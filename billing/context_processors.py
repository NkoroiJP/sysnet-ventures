from .models import CompanyProfile, ContactMessage

def company_info(request):
    return {
        'company': CompanyProfile.objects.first()
    }

def unread_count(request):
    """Add unread message count to all templates"""
    if request.user.is_authenticated:
        return {'unread_count': ContactMessage.objects.filter(is_read=False).count()}
    return {'unread_count': 0}
