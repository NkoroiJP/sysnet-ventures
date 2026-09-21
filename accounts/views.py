"""Authentication views: throttled login, logout, password change."""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .audit import audit
from .forms import StyledAuthenticationForm, StaffPasswordChangeForm
from .throttle import client_ip


def _redirect_target(user):
    if user.is_client:
        return 'portal_dashboard'
    if user.is_staff_user or user.is_superuser:
        return 'dashboard'
    return 'home'


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_redirect_target(request.user))

    if request.method == 'POST':
        form = StyledAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            audit('login', object_type='User', object_id=user.pk, object_repr=str(user), user=user, ip=client_ip(request))
            return redirect(_redirect_target(user))
        # fall through: shows errors; the throttle backend may have blocked
    else:
        form = StyledAuthenticationForm(request)

    return render(request, 'registration/login.html', {'form': form})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        audit('logout', object_type='User', object_id=request.user.pk, object_repr=str(request.user), user=request.user, ip=client_ip(request))
    logout(request)
    return redirect('home')


def change_password(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        form = StaffPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, request.user)
            audit('admin', object_type='User', object_id=request.user.pk, object_repr='password changed', user=request.user, ip=client_ip(request))
            messages.success(request, 'Password updated.')
            return redirect('change_password')
    else:
        form = StaffPasswordChangeForm(request.user)
    return render(request, 'registration/password_change_form.html', {'form': form})
