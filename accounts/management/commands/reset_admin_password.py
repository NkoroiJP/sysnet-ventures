"""Reset a user's password non-interactively (for locked-out admins)."""
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Reset a user's password: reset_admin_password <username> <new_password>"

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('new_password')

    def handle(self, *args, **options):
        username = options['username']
        password = options['new_password']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User {username!r} not found.')

        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(password, user)
        except Exception as warnings:
            self.stdout.write(self.style.WARNING(f'Weak password warnings: {warnings}'))

        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f'Password for {username} has been reset.'))
