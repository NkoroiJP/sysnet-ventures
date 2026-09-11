#!/usr/bin/env bash
set -o errexit
set -o pipefail

# Wait for the database to accept connections (Postgres in production).
python - <<'PY'
import os, sys, time

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    sys.exit(0)  # SQLite: file-based, no wait needed

try:
    import psycopg

    def connect():
        return psycopg.connect(database_url)
except ImportError:
    import psycopg2

    def connect():
        return psycopg2.connect(database_url)

for attempt in range(30):
    try:
        connect().close()
        print("Database is ready.", flush=True)
        break
    except Exception as exc:
        print(f"Waiting for database... ({attempt + 1}/30): {exc}", flush=True)
        time.sleep(2)
else:
    sys.exit("Database did not become ready in time.")
PY

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Optional: auto-create a superuser on first boot (set DJANGO_SUPERUSER_* env vars)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py shell <<'PY'
from django.contrib.auth import get_user_model
import os
User = get_user_model()
if not User.objects.filter(username=os.environ["DJANGO_SUPERUSER_USERNAME"]).exists():
    User.objects.create_superuser(
        os.environ["DJANGO_SUPERUSER_USERNAME"],
        os.environ.get("DJANGO_SUPERUSER_EMAIL", ""),
        os.environ["DJANGO_SUPERUSER_PASSWORD"],
    )
    print("Superuser created.")
PY
fi

exec gunicorn sysnet_core.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
