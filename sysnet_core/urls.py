"""Root URL configuration."""
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from accounts import views as accounts_views
from .sitemap import StaticViewSitemap, ServiceSitemap
from .views import healthz, protected_media, robots_txt

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('billing/', include('billing.urls')),
    path('portal/login/', accounts_views.login_view, name='portal_login'),
    path('', include('website.urls')),
    path('sitemap.xml', sitemap, {'sitemaps': {
        'static': StaticViewSitemap,
        'services': ServiceSitemap,
    }}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', robots_txt, name='robots'),
    path('healthz', healthz, name='healthz'),
    # Uploaded files always served through permission checks (logos public,
    # payment evidence staff-only) — in dev AND production.
    path('media/<path:path>', protected_media, name='protected_media'),
]

handler404 = 'sysnet_core.views.handler404'
handler500 = 'sysnet_core.views.handler500'
