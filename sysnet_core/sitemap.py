from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from billing.models import ServicePage


class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = 'weekly'

    def items(self):
        return ['home', 'about', 'service_list', 'product_catalog', 'portfolio', 'contact', 'request_quote']

    def location(self, item):
        return reverse(item)


class ServiceSitemap(Sitemap):
    priority = 0.9
    changefreq = 'monthly'

    def items(self):
        return ServicePage.objects.filter(is_active=True)

    def location(self, obj):
        return reverse('service_detail', args=[obj.slug])

    def lastmod(self, obj):
        return None
