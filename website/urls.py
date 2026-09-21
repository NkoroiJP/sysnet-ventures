from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('services/', views.service_list, name='service_list'),
    path('services/<slug:slug>/', views.service_detail, name='service_detail'),
    path('products/', views.product_catalog, name='product_catalog'),
    path('portfolio/', views.portfolio, name='portfolio'),
    path('contact/', views.contact, name='contact'),
    path('request-quote/', views.request_quote, name='request_quote'),
]
