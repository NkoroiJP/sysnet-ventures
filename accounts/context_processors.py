"""Portal-facing context: current client record (if any)."""
from django.conf import settings


def portal_info(request):
    user = getattr(request, 'user', None)
    ctx = {}
    if user is not None and user.is_authenticated and user.is_client:
        ctx['portal_client'] = user.client
    return ctx
