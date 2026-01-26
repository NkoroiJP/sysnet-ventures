from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    
    # Customers
    path('customer/', views.customer_list, name='customer_list'),
    path('customer/add/', views.customer_create, name='customer_create'),
    path('customer/<int:pk>/edit/', views.customer_update, name='customer_update'),

    # Quotations
    path('quotation/', views.quotation_list, name='quotation_list'),
    path('quotation/add/', views.quotation_create, name='quotation_create'),
    path('quotation/<int:pk>/', views.quotation_detail, name='quotation_detail'),
    path('quotation/<int:pk>/edit/', views.quotation_update, name='quotation_update'),
    path('quotation/<int:pk>/convert/', views.convert_quote_to_invoice, name='convert_quote_to_invoice'),

    # Invoices
    path('invoice/', views.invoice_list, name='invoice_list'),
    path('invoice/add/', views.invoice_create, name='invoice_create'),
    path('invoice/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoice/<int:pk>/edit/', views.invoice_update, name='invoice_update'),
    path('invoice/<int:invoice_pk>/payment/', views.add_receipt, name='add_receipt'),

    # Receipts
    path('receipt/', views.receipt_list, name='receipt_list'),
    path('receipt/<int:pk>/', views.receipt_detail, name='receipt_detail'),
]