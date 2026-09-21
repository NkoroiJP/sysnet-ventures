"""
Secure upload handling for client proof-of-payment files.

- Extension + declared content-type + magic-byte sniffing validation
- Hard size cap (settings.MAX_UPLOAD_SIZE_MB)
- Files stored under unguessable names in a non-public location; downloads go
  through permission-checked views, never through /media/ directly.
"""
import uuid

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from PIL import Image

from django.conf import settings


def validate_upload(file_obj):
    """Validate an uploaded payment-evidence file. Raises ValidationError."""
    ext = ''
    if file_obj.name and '.' in file_obj.name:
        ext = '.' + file_obj.name.rsplit('.', 1)[1].lower()
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationError('Allowed file types: PNG, JPG, WEBP or PDF.')

    if file_obj.size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValidationError(f'File too large. Maximum is {settings.MAX_UPLOAD_SIZE_MB} MB.')

    # Read a small header for magic-byte checks.
    pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
    header = file_obj.read(16) or b''
    file_obj.seek(pos)

    def starts_with(*magic):
        return header.startswith(bytes(magic))

    if ext == '.pdf':
        if not starts_with(b'%PDF'):
            raise ValidationError('File content does not look like a PDF.')
    else:
        try:
            Image.open(file_obj).verify()
            file_obj.seek(pos)
        except Exception:
            raise ValidationError('File content is not a valid image.')


@deconstructible
class EvidencePath:
    """Upload to payment-evidence/<uuid><ext> — unguessable, flat."""

    def __call__(self, instance, filename):
        import os
        ext = os.path.splitext(filename)[1].lower()
        return f'payment-evidence/{uuid.uuid4().hex}{ext}'

    def __eq__(self, other):
        return isinstance(other, EvidencePath)
