"""Server-side authorization decorators. Hiding buttons is not enough."""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from accounts.models import User


def _require(request, predicate):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not predicate(request.user):
        raise PermissionDenied
    return None


def staff_required(view):
    """Any internal staff role."""
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        block = _require(request, lambda u: u.is_staff_user or u.is_superuser)
        return block or view(request, *args, **kwargs)
    return _wrapped


def finance_required(view):
    """Finance and above."""
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        block = _require(request, lambda u: u.is_finance or u.is_superuser)
        return block or view(request, *args, **kwargs)
    return _wrapped


def superadmin_required(view):
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        block = _require(request, lambda u: u.is_super_admin)
        return block or view(request, *args, **kwargs)
    return _wrapped


def client_of_required(model):
    """Portal view guard: client users may only touch their own records.

    Usage: @client_of_required(Invoice) with kwargs containing 'pk' or 'number'.
    Staff bypass. Raises PermissionDenied on cross-client access (IDOR guard).
    """
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.is_staff_user or request.user.is_superuser:
                return view(request, *args, **kwargs)
            if not request.user.is_client or request.user.client_id is None:
                raise PermissionDenied
            obj = get_object_or_404(model, pk=kwargs.get('pk'))
            owner = getattr(obj, 'client_id', None)
            if owner != request.user.client_id:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return _wrapped
    return decorator
