FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Pillow / psycopg / xhtml2pdf (reportlab)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq5 \
    libjpeg-dev \
    zlib1g-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

# Non-root runtime; writable dirs for gunicorn, media and static collection
RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/data /app/media /app/staticfiles /home/app \
    && chown -R app:app /app /home/app
USER app

ENV HOME=/home/app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["/app/entrypoint.sh"]
