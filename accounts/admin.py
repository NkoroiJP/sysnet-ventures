from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, LoginAttempt, AuditLog


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'client', 'is_active')
    list_filter = ('role', 'is_active')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Sysnet role', {'fields': ('role', 'phone', 'client')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Sysnet role', {'fields': ('role', 'phone', 'client')}),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'action', 'object_type', 'object_repr')
    list_filter = ('action', 'object_type')
    search_fields = ('object_repr', 'detail', 'user__username')
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('username', 'ip', 'successful', 'throttled', 'attempted_at')
    list_filter = ('successful', 'throttled')
    readonly_fields = [f.name for f in LoginAttempt._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
