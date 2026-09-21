"""Project-level views: health check, robots.txt, protected media, error handlers."""
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.static import serve as _static_serve


def healthz(request):
    """Container health check: verifies the DB is reachable."""
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        db_ok = True
    except Exception:
        db_ok = False
    if not db_ok:
        return JsonResponse({'status': 'error', 'database': False}, status=503)
    return JsonResponse({'status': 'ok', 'database': True})


def protected_media(request, path):
    """Serve uploaded files through permission checks.

    In production /media/ must never be a public directory: it can contain
    client proof-of-payment documents. Access policy:

    - logos/                 -> public (site branding)
    - payment-evidence/      -> authenticated internal staff only
    - anything else          -> authenticated users

    django.views.static.serve is used for the actual file response; it is
    safe against path traversal and sets sane content types. Traffic volume
    for these files is tiny; put nginx X-Accel in front if that ever changes.
    """
    user = request.user
    if path.startswith('payment-evidence/'):
        if not user.is_authenticated:
            return redirect(f'{reverse("portal_login")}?next={request.get_full_path()}')
        if not (getattr(user, 'is_staff_user', False) or user.is_superuser):
            from django.http import Http404
            raise Http404('Not found')
    elif not path.startswith('logos/'):
        if not user.is_authenticated:
            return redirect(f'{reverse("portal_login")}?next={request.get_full_path()}')
    return _static_serve(request, path, document_root=str(settings.MEDIA_ROOT))


def robots_txt(request):
    lines = ['User-agent: *', 'Disallow: /billing/', 'Disallow: /accounts/', 'Disallow: /admin/', 'Disallow: /media/payment-evidence/']
    if not settings.DEBUG:
        lines.append('Disallow: /portal/')
    sitemap_url = f'{request.scheme}://{request.get_host()}/sitemap.xml'
    lines.append(f'Sitemap: {sitemap_url}')
    return HttpResponse('\n'.join(lines), content_type='text/plain')


def handler404(request, exception=None):
    return render_safe(request, '404.html', status=404)


def handler500(request):
    return render_safe(request, '500.html', status=500)


def render_safe(request, template, status):
    """Error handlers must never raise, even if templates are missing."""
    from django.shortcuts import render
    try:
        return render(request, template, status=status)
    except Exception:
        return HttpResponse(f'Error {status}', status=status, content_type='text/plain')
