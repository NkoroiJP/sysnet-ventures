"""
Role-based user model for the Sysnet platform.

Roles map to intent rather than raw Django permissions:
- super_admin: full access to every module
- finance:     quotations, invoices, payments, receipts, credit notes, reports
- sales:       leads, clients, catalog, enquiries, quotations
- client:      portal access restricted to their own client record
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    SUPER_ADMIN = 'super_admin'
    FINANCE = 'finance'
    SALES = 'sales'
    CLIENT = 'client'

    ROLE_CHOICES = [
        (SUPER_ADMIN, 'Super Admin'),
        (FINANCE, 'Finance / Accountant'),
        (SALES, 'Sales / Staff'),
        (CLIENT, 'Client'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=SALES)
    phone = models.CharField(max_length=32, blank=True)
    client = models.ForeignKey(
        'billing.Client', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='portal_users', help_text='Required for users with the Client role.',
    )
    is_active = models.BooleanField(default=True)  # explicit for activation toggling

    class Meta:
        ordering = ['username']

    def __str__(self):
        return self.get_full_name() or self.username

    # ---- role helpers -------------------------------------------------
    @property
    def is_super_admin(self):
        return self.role == self.SUPER_ADMIN or self.is_superuser

    @property
    def is_finance(self):
        return self.role == self.FINANCE or self.is_super_admin

    @property
    def is_sales(self):
        return self.role == self.SALES or self.is_finance

    @property
    def is_client(self):
        return self.role == self.CLIENT

    @property
    def is_staff_user(self):
        """Any internal staff role (not a portal client)."""
        return self.is_sales  # sales-or-higher ladder covers all staff roles

    def can_manage_settings(self):
        return self.is_super_admin

    def can_manage_users(self):
        return self.is_super_admin

    def can_manage_finance(self):
        """Invoices, payments, receipts, credit notes."""
        return self.is_finance

    def can_issue_invoice(self):
        return self.is_finance

    def can_manage_clients(self):
        return self.is_sales

    def can_manage_catalog(self):
        return self.is_sales


class LoginAttempt(models.Model):
    """One row per login attempt, used for throttling and security review."""

    username = models.CharField(max_length=255, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    successful = models.BooleanField(default=False)
    throttled = models.BooleanField(default=False)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-attempted_at']
        indexes = [
            models.Index(fields=['username', 'attempted_at']),
            models.Index(fields=['ip', 'attempted_at']),
        ]

    def __str__(self):
        state = 'ok' if self.successful else ('throttled' if self.throttled else 'failed')
        return f'{self.username} [{state}] at {self.attempted_at:%Y-%m-%d %H:%M}'


class AuditLog(models.Model):
    """Immutable trail for sensitive financial and administrative actions."""

    ACTION_CHOICES = [
        ('create', 'Created'),
        ('update', 'Updated'),
        ('status', 'Status changed'),
        ('send', 'Sent'),
        ('convert', 'Converted'),
        ('void', 'Voided'),
        ('credit', 'Credit note issued'),
        ('payment', 'Payment recorded'),
        ('verify', 'Payment verified'),
        ('auth', 'Authentication event'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('admin', 'Admin action'),
    ]

    user = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='audit_entries')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    object_type = models.CharField(max_length=64)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    detail = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['object_type', 'object_id'])]

    def __str__(self):
        return f'{self.action} {self.object_type}#{self.object_id} by {self.user}'
