"""
Email notification service.

- Branded HTML templates with plain-text fallback
- Retries transient failures (max 3 attempts)
- Every send is tracked in NotificationLog (status tracking requirement)
- Failures NEVER break financial transactions: callers wrap sends in try/except
"""
import logging

from django.conf import settings as dj_settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import CompanySettings, NotificationLog

logger = logging.getLogger('billing.emails')

MAX_ATTEMPTS = 3


def _company():
    return CompanySettings.load()


def send_notification(template_base, context, subject, to_emails, category='general', log_purpose=''):
    """Render {template_base}.html + {template_base}.txt and send with retry."""
    company = _company()
    context.setdefault('company', company)
    context.setdefault('site_url', '')

    html_body = render_to_string(f'emails/{template_base}.html', context)
    text_body = render_to_string(f'emails/{template_base}.txt', context)

    log = NotificationLog.objects.create(
        purpose=log_purpose or template_base, recipient=', '.join(to_emails),
        subject=subject, status=NotificationLog.PENDING,
    )

    sent_ok = False
    last_error = ''
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            msg = EmailMultiAlternatives(
                subject=subject, body=text_body,
                from_email=dj_settings.DEFAULT_FROM_EMAIL, to=list(to_emails),
            )
            msg.attach_alternative(html_body, 'text/html')
            msg.send(fail_silently=False)
            sent_ok = True
            break
        except Exception as exc:  # transient SMTP issues
            last_error = str(exc)
            logger.warning('Email attempt %s/%s failed (%s): %s', attempt, MAX_ATTEMPTS, log_purpose, exc)

    log.status = NotificationLog.SENT if sent_ok else NotificationLog.FAILED
    log.error_message = '' if sent_ok else last_error[:500]
    log.attempts = MAX_ATTEMPTS if not sent_ok else log.attempts
    log.save()

    if not sent_ok:
        logger.error('Email delivery failed permanently: %s (%s)', log_purpose, last_error)
    return sent_ok


# ---------------------------------------------------------------- specific sends

def notify_new_enquiry(enquiry):
    staff = (dj_settings.STAFF_NOTIFY_EMAIL or _company().email or '').strip()
    if not staff:
        return False
    return send_notification(
        'new_enquiry',
        {'enquiry': enquiry},
        f'New enquiry from {enquiry.name}',
        [staff], log_purpose='new_enquiry',
    )


def notify_contact_message(message):
    staff = (dj_settings.STAFF_NOTIFY_EMAIL or _company().email or '').strip()
    if not staff:
        return False
    return send_notification(
        'contact_message',
        {'message': message},
        f'Website contact: {message.get_category_display()}',
        [staff], log_purpose='contact_message',
    )


def notify_quotation_sent(quotation, portal_link=''):
    if not quotation.client.email:
        return False
    return send_notification(
        'quotation_sent',
        {'quotation': quotation, 'portal_link': portal_link},
        f'Quotation {quotation.number} from {_company().name}',
        [quotation.client.email], log_purpose='quotation_sent',
    )


def notify_quotation_decision(quotation, accepted):
    staff = (dj_settings.STAFF_NOTIFY_EMAIL or _company().email or '').strip()
    if not staff:
        return False
    verb = 'accepted' if accepted else 'rejected'
    return send_notification(
        'quotation_decision',
        {'quotation': quotation, 'accepted': accepted},
        f'Quotation {quotation.number} {verb}',
        [staff], log_purpose='quotation_decision',
    )


def notify_invoice_sent(invoice, portal_link=''):
    if not invoice.client.email:
        return False
    return send_notification(
        'invoice_sent',
        {'invoice': invoice, 'portal_link': portal_link},
        f'Invoice {invoice.number} from {_company().name}',
        [invoice.client.email], log_purpose='invoice_sent',
    )


def notify_payment_confirmed(payment, receipt):
    if not payment.client.email:
        return False
    return send_notification(
        'payment_confirmed',
        {'payment': payment, 'receipt': receipt},
        f'Payment received — receipt {receipt.number}',
        [payment.client.email], log_purpose='payment_confirmed',
    )
