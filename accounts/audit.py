"""Immutable audit-trail helper. Never update or delete rows."""
from functools import wraps

from .models import AuditLog


def audit(action, obj=None, *, object_type='', object_id='', object_repr='', detail='', user=None, ip=None):
    """Record an audit entry. Safe to call with an anonymous user."""
    return AuditLog.objects.create(
        user=user,
        action=action,
        object_type=object_type or (obj._meta.label if obj is not None else ''),
        object_id=object_id or (str(obj.pk) if obj is not None and hasattr(obj, 'pk') else ''),
        object_repr=object_repr or (str(obj)[:255] if obj is not None else ''),
        detail=detail or '',
        ip=ip,
    )


def audited(action, get_obj=None, object_type=''):
    """Decorator: wraps a view, logging `action` against a callable-resolved object.

    Usage:
        @audited('void', lambda request, pk: get_object_or_404(Invoice, pk=pk), 'Invoice')
        def invoice_void(request, pk): ...
    """
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            response = view(request, *args, **kwargs)
            try:
                obj = get_obj(request, *args, **kwargs) if get_obj else None
                audit(
                    action, obj, object_type=object_type,
                    user=request.user if getattr(request, 'user', None) and request.user.is_authenticated else None,
                    ip=_client_ip(request),
                )
            except Exception:
                pass
            return response
        return _wrapped
    return decorator


def _client_ip(request):
    from accounts.throttle import client_ip
    return client_ip(request)
