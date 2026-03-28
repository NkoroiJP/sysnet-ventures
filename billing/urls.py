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
    path('quotation/<int:pk>/pdf/', views.quotation_pdf, name='quotation_pdf'),

    # Invoices
    path('invoice/', views.invoice_list, name='invoice_list'),
    path('invoice/add/', views.invoice_create, name='invoice_create'),
    path('invoice/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoice/<int:pk>/edit/', views.invoice_update, name='invoice_update'),
    path('invoice/<int:invoice_pk>/payment/', views.add_receipt, name='add_receipt'),
    path('invoice/<int:pk>/pdf/', views.invoice_pdf, name='invoice_pdf'),

    # Receipts
    path('receipt/', views.receipt_list, name='receipt_list'),
    path('receipt/<int:pk>/', views.receipt_detail, name='receipt_detail'),
    path('receipt/<int:pk>/pdf/', views.receipt_pdf, name='receipt_pdf'),

    # Products
    path('product/', views.product_list, name='product_list'),
    path('product/add/', views.product_create, name='product_create'),
    path('product/<int:pk>/edit/', views.product_update, name='product_update'),

    # Messages / Contact Form
    path('messages/', views.message_list, name='message_list'),
    path('messages/<int:pk>/', views.message_detail, name='message_detail'),
    path('messages/<int:pk>/mark-read/', views.message_mark_read, name='message_mark_read'),
    path('messages/<int:pk>/mark-unread/', views.message_mark_unread, name='message_mark_unread'),
    path('messages/<int:pk>/delete/', views.message_delete, name='message_delete'),

    # Settings
    path('settings/', views.company_settings, name='company_settings'),

    # API
    path('api/product/<int:pk>/', views.product_api, name='product_api'),
]