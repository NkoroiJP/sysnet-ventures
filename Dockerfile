# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies for xhtml2pdf, Pillow and psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2-dev \
    pkg-config \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    libffi-dev \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Make entrypoint executable just in case
RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/data /app/media /app/staticfiles \
    && useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Run the entrypoint script
CMD ["/app/entrypoint.sh"]
