"""
Login throttling backend.

Counts failed logins per username and per IP inside a sliding window. When the
limit is exceeded, authentication fails closed for the remainder of the window
even if the credentials are correct. Records are pruned opportunistically.
"""
import logging

from django.contrib.auth.backends import ModelBackend
from django.utils import timezone

from .models import LoginAttempt

logger = logging.getLogger('accounts.throttle')


def client_ip(request):
    """Best-effort client IP extraction (works behind the nginx reverse proxy)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


class ThrottledModelBackend(ModelBackend):
    """ModelBackend that fail-closes when too many recent failures exist."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if request is None:
            # Programmatic authenticate (e.g. `createsuperuser`): skip throttle.
            return super().authenticate(request, username=username, password=password, **kwargs)

        ip = client_ip(request)
        window = self._window_seconds()
        limit = self._limit()

        if self._is_throttled(username or '', ip, window, limit):
            LoginAttempt.objects.create(username=(username or '')[:255], ip=ip, successful=False, throttled=True)
            logger.warning('Throttled login attempt for user=%r from %s', username, ip)
            return None

        user = super().authenticate(request, username=username, password=password, **kwargs)

        LoginAttempt.objects.create(
            username=(username or '')[:255], ip=ip,
            successful=user is not None,
        )
        self._prune(window)
        return user

    # ---- internals ----------------------------------------------------
    def _limit(self):
        from django.conf import settings
        return settings.THROTTLE_CONFIG['login']['limit']

    def _window_seconds(self):
        from django.conf import settings
        return settings.THROTTLE_CONFIG['login']['window_seconds']

    def _is_throttled(self, username, ip, window, limit):
        since = timezone.now() - timezone.timedelta(seconds=window)
        by_user = LoginAttempt.objects.filter(
            username=username.lower(), successful=False, throttled=False, attempted_at__gte=since,
        ).count()
        if by_user >= limit:
            return True
        by_ip = LoginAttempt.objects.filter(
            ip=ip, successful=False, throttled=False, attempted_at__gte=since,
        ).count()
        return by_ip >= limit

    def _prune(self, window):
        cutoff = timezone.now() - timezone.timedelta(seconds=window * 4)
        LoginAttempt.objects.filter(attempted_at__lt=cutoff).delete()
