from django.urls import path

from . import views_staff, views_documents, views_portal

staff_patterns = [
    path('', views_staff.dashboard, name='dashboard'),

    # Clients
    path('clients/', views_staff.client_list, name='client_list'),
    path('clients/add/', views_staff.client_create, name='client_create'),
    path('clients/<int:pk>/', views_staff.client_detail, name='client_detail'),
    path('clients/<int:pk>/edit/', views_staff.client_update, name='client_update'),
    path('clients/<int:pk>/archive/', views_staff.client_archive, name='client_archive'),
    path('clients/<int:pk>/statement/', views_documents.client_statement, name='client_statement'),
    path('clients/<int:pk>/statement/pdf/', views_documents.client_statement_pdf, name='client_statement_pdf'),

    # Quotations
    path('quotations/', views_documents.quotation_list, name='quotation_list'),
    path('quotations/add/', views_documents.quotation_create, name='quotation_create'),
    path('quotations/<int:pk>/', views_documents.quotation_detail, name='quotation_detail'),
    path('quotations/<int:pk>/send/', views_documents.quotation_send, name='quotation_send'),
    path('quotations/<int:pk>/revise/', views_documents.quotation_revise, name='quotation_revise'),
    path('quotations/<int:pk>/convert/', views_documents.quotation_convert, name='quotation_convert'),
    path('quotations/<int:pk>/delete/', views_documents.quotation_delete, name='quotation_delete'),
    path('quotations/<int:pk>/pdf/', views_documents.quotation_pdf, name='quotation_pdf'),

    # Invoices
    path('invoices/', views_documents.invoice_list, name='invoice_list'),
    path('invoices/add/', views_documents.invoice_create, name='invoice_create'),
    path('invoices/<int:pk>/', views_documents.invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/issue/', views_documents.invoice_issue, name='invoice_issue'),
    path('invoices/<int:pk>/void/', views_documents.invoice_void, name='invoice_void'),
    path('invoices/<int:pk>/pdf/', views_documents.invoice_pdf, name='invoice_pdf'),
    path('invoices/<int:pk>/csv/', views_documents.invoice_csv, name='invoice_csv'),
    path('invoices/<int:invoice_pk>/payment/', views_documents.payment_record, name='payment_record'),
    path('invoices/<int:pk>/credit-note/', views_documents.credit_note_create, name='credit_note_create'),
    path('invoices/export/', views_documents.reports_export_csv, name='reports_export_csv'),

    # Payments
    path('payments/', views_documents.payment_list, name='payment_list'),
    path('payments/<int:pk>/', views_documents.payment_detail, name='payment_detail'),
    path('payments/<int:pk>/allocate/', views_documents.payment_allocate, name='payment_allocate'),
    path('payments/<int:pk>/deallocate/<int:allocation_pk>/', views_documents.payment_deallocate, name='payment_deallocate'),
    path('submissions/<int:submission_pk>/verify/', views_documents.payment_verify, name='payment_verify'),

    # Receipts
    path('receipts/', views_documents.receipt_list, name='receipt_list'),
    path('receipts/<int:pk>/', views_documents.receipt_detail, name='receipt_detail'),
    path('receipts/<int:pk>/pdf/', views_documents.receipt_pdf, name='receipt_pdf'),

    # Catalog
    path('catalog/', views_staff.product_list, name='product_list'),
    path('catalog/add/', views_staff.product_create, name='product_create'),
    path('catalog/<int:pk>/edit/', views_staff.product_update, name='product_update'),
    path('catalog/<int:pk>/archive/', views_staff.product_archive, name='product_archive'),

    # Enquiries
    path('enquiries/', views_staff.enquiry_list, name='enquiry_list'),
    path('enquiries/<int:pk>/status/', views_staff.enquiry_set_status, name='enquiry_set_status'),
    path('messages/<int:pk>/toggle-read/', views_staff.message_mark_read, name='message_mark_read'),
    path('messages/<int:pk>/delete/', views_staff.message_delete, name='message_delete'),

    # Settings (super admin)
    path('settings/', views_staff.company_settings, name='company_settings'),
    path('settings/tax/', views_staff.tax_categories, name='tax_categories'),
    path('settings/tax/<int:pk>/edit/', views_staff.tax_category_update, name='tax_category_update'),
    path('settings/users/', views_staff.user_list, name='user_list'),
    path('settings/users/add/', views_staff.user_create, name='user_create'),
    path('settings/users/<int:pk>/edit/', views_staff.user_update, name='user_update'),
    path('settings/users/<int:pk>/toggle/', views_staff.user_toggle_active, name='user_toggle_active'),
    path('settings/audit/', views_staff.audit_log, name='audit_log'),
]

# Portal routes are mounted at /billing/portal/... (see paths below).
portal_patterns = [
    path('portal/dashboard/', views_portal.portal_dashboard, name='portal_dashboard'),
    path('portal/quotations/<int:pk>/', views_portal.portal_quotation, name='portal_quotation'),
    path('portal/quotations/<int:pk>/decide/', views_portal.portal_quotation_decide, name='portal_quotation_decide'),
    path('portal/quotations/<int:pk>/pdf/', views_portal.portal_quotation_pdf, name='portal_quotation_pdf'),
    path('portal/invoices/<int:pk>/', views_portal.portal_invoice, name='portal_invoice'),
    path('portal/invoices/<int:pk>/pdf/', views_portal.portal_invoice_pdf, name='portal_invoice_pdf'),
    path('portal/payments/', views_portal.portal_payments, name='portal_payments'),
    path('portal/payments/submit/', views_portal.portal_submit_payment, name='portal_submit_payment'),
    path('portal/receipts/<int:pk>/', views_portal.portal_receipt, name='portal_receipt'),
    path('portal/receipts/<int:pk>/pdf/', views_portal.portal_receipt_pdf, name='portal_receipt_pdf'),
    path('portal/statement/', views_portal.portal_statement, name='portal_statement'),
    path('portal/statement/pdf/', views_portal.portal_statement_pdf, name='portal_statement_pdf'),
    path('portal/service-request/', views_portal.portal_service_request, name='portal_service_request'),
    path('portal/profile/', views_portal.portal_profile, name='portal_profile'),
]

urlpatterns = staff_patterns + portal_patterns
