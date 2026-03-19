from .models import CompanyProfile

def company_info(request):
    return {
        'company': CompanyProfile.objects.first()
    }
