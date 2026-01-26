# Sysnet Ventures Platform

A modern web application for Sysnet Ventures, featuring a public landing page and a comprehensive billing/management dashboard.

## Tech Stack
- **Backend:** Django 5 (Python 3.11)
- **Frontend:** HTML5 + Tailwind CSS (via CDN for speed)
- **Database:** SQLite (Lightweight, file-based)
- **Infrastructure:** Docker & Docker Compose

## Getting Started

### Prerequisites
- Docker and Docker Compose installed on your machine.

### Running the App
1. **Start the server:**
   ```bash
   docker compose up
   ```
   (Add `-d` to run in background: `docker compose up -d`)

2. **Access the site:**
   - **Public Site:** [http://localhost:8000](http://localhost:8000)
   - **Dashboard:** [http://localhost:8000/billing/](http://localhost:8000/billing/)
   - **Admin Panel:** [http://localhost:8000/admin/](http://localhost:8000/admin/)

### Login Credentials
A default superuser has been created for you:
- **Username:** `admin`
- **Password:** `admin`

**Note:** Please change this password immediately upon logging in for security.

## Features
- **Public Landing Page:** Showcases services (Software, Network, CCTV, etc.) with a modern design.
- **Quotation System:** Create quotes for customers with multiple items.
- **Invoicing:** Convert accepted quotes into invoices with one click in the Admin panel.
- **Receipts:** Track payments against invoices.
- **Dashboard:** View total revenue, pending invoices, and recent activity.

## Development
- To add new dependencies, edit `requirements.txt` and run `docker compose build`.
- To make database changes, run:
  ```bash
  docker compose run --rm web python manage.py makemigrations
  docker compose run --rm web python manage.py migrate
  ```
