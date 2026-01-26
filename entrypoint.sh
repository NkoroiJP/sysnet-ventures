#!/usr/bin/env bash
# Exit on error
set -o errexit

# Apply database migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Start Gunicorn
gunicorn sysnet_core.wsgi:application --bind 0.0.0.0:8000
