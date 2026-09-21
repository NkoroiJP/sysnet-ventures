#!/usr/bin/env bash
set -o errexit
set -o pipefail

cd /app

# --- Wait for the database -------------------------------------------------
python - <<'PY'
import os, sys, time

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    print("No DATABASE_URL set — using SQLite, skipping wait.")
    sys.exit(0)

try:
    import psycopg
    def connect():
        return psycopg.connect(database_url, connect_timeout=3)
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

# --- Migrate + collect static ----------------------------------------------
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# --- Safe defaults: tax categories, company settings, service pages --------
python manage.py seed_defaults

# --- Optional first-boot superuser (set env vars to enable) ----------------
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
if username and password and not User.objects.filter(username=username).exists():
    User.objects.create_superuser(
        username,
        os.environ.get("DJANGO_SUPERUSER_EMAIL", ""),
        password,
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
