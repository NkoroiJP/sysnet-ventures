# Sysnet Ventures Platform

A comprehensive business management system designed for Sysnet Ventures, featuring a public-facing website with contact functionality and an integrated billing/dashboard platform for managing customers, quotations, invoices, receipts, products, and internal communications.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Getting Started](#getting-started)
- [User Guide](#user-guide)
- [Development](#development)
- [Project Structure](#project-structure)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

---

## Overview

Sysnet Ventures Platform is a full-stack business management solution that combines:

1. **Public Website** - A professional landing page showcasing services with an integrated contact form
2. **Management Dashboard** - A secure, authenticated area for managing all business operations
3. **Messaging System** - Internal chat-style interface for handling customer inquiries from the contact form

The platform streamlines business workflows from lead generation (contact form) to quotation, invoicing, and payment tracking.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Django 5.2, Python 3.11 |
| **Frontend** | HTML5, Tailwind CSS, Font Awesome Icons, Vanilla JavaScript |
| **Database** | SQLite (development, `data/db.sqlite3`) / PostgreSQL via `DATABASE_URL` |
| **PDF Generation** | xhtml2pdf |
| **Image Processing** | Pillow |
| **Infrastructure** | Docker, Docker Compose |
| **Web Server** | Django Development Server / Gunicorn (production) |
| **Static Files** | WhiteNoise |

---

## Features

### Public Website

- **Landing Page** - Modern, responsive design showcasing company services
- **Services Section** - Displays offerings: Software Development, Network Installation, CCTV & Security, Repair & Maintenance, Sales & Accessories, Technical Consultancy
- **Contact Form** - Allows visitors to send inquiries directly to the dashboard messaging system

### Dashboard & Billing

#### Dashboard Overview
- Real-time financial metrics (total revenue, pending invoices)
- Quick stats (total customers, active quotes)
- Recent activity feed

#### Customer Management
- Create, edit, and view customer records
- Store contact information and addresses
- View customer history#### Quotation System

- Professional document numbers (`QTN-2026-0001`) generated automatically
- Create quotations with multiple line items, live totals and tax
- Auto-fill product details (name, price, description) when selecting products
- Add line items dynamically without re-saving
- One-click status workflow: Draft → Sent → Accepted/Rejected → **Convert to Invoice**
- Conversion is guarded: quotes can only be converted once
- Generate and download PDF quotations#### Invoicing

- Create invoices from scratch or convert from quotations (tax rate and notes carry over)
- Auto-fill product details when selecting from the product catalog
- Track payment status (Pending, Paid, Overdue — overdue is computed automatically from the due date)
- Record partial or full payments; invoices flip to **Paid** automatically when settled
- Payment progress bar and balance due on the invoice page
- Generate and download professional PDF invoices (branded, with PAID stamp)
- View payment history per invoice; delete a payment to reopen the invoice

#### Receipt Management
- Record payments against invoices
- Generate official payment receipts as compact single-page PDFs
- Track payment methods and add notes
- View receipt history#### Product & Services Catalog

- Maintain a catalog of products and services
- Define pricing and descriptions
- Auto-populate quotation/invoice line items
- Categorize as Service or Product
- Archive products instead of deleting so historical documents stay intact

#### Company Settings
- Configure company profile (name, logo, contact info, tax number)
- Company details appear on all PDF documents
- Upload and manage company logo

#### Messaging System
- **Inbox** - View all contact form submissions in a chat-style interface
- **Unread Counter** - Red badge on sidebar shows number of unread messages
- **Read/Unread Status** - Toggle message status; unread messages highlighted
- **Quick Actions** - Mark as read/unread, delete, reply via email
- **Message Detail** - Full conversation view with sender information

### PDF Generation

All PDF documents are professionally formatted and include:

- Company branding and contact information
- Customer/client details
- Itemized listings with quantities and prices
- Totals, taxes, and balances
- Status indicators (Paid, Pending, etc.)
- Signature and stamp areas

**Available PDFs:**
- Quotations
- Invoices
- Payment Receipts (compact single-page design)

---

## Getting Started

### Prerequisites

- **Docker** (version 20.10 or higher)
- **Docker Compose** (version 2.0 or higher)

Verify installation:
```bash
docker --version
docker compose version
```

### Quick Start

1. **Clone the repository** (if not already done):
   ```bash
   git clone <repository-url>
   cd sysnet-ventures
   ```

2. **Configure the environment** (copy the template and edit):
   ```bash
   cp .env.example .env
   ```

3. **Start the application**:
   ```bash
   docker compose up
   ```

   Or run in background:
   ```bash
   docker compose up -d
   ```

   For production with the bundled Postgres profile:
   ```bash
   docker compose --profile postgres up -d
   ```

3. **Access the application**:
   - **Public Website**: [http://localhost:8000](http://localhost:8000)
   - **Dashboard**: [http://localhost:8000/billing/](http://localhost:8000/billing/)
   - **Admin Panel**: [http://localhost:8000/admin/](http://localhost:8000/admin/)

### First Login

Create a superuser (or set `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` in `.env` to have one created automatically on first boot):

```bash
docker compose run --rm web python manage.py createsuperuser
```

> ⚠️ **Security Notice**: Never ship default credentials to production.

---

## User Guide

### Creating a Quotation

1. Navigate to **Quotations** → **Add Quotation**
2. Select customer (or create new)
3. Set date and status
4. Add line items:
   - Select a product/service from dropdown (price and description auto-fill)
   - Or enter custom description, quantity, and unit price
5. Click **Save Quotation**
6. View, edit, or download as PDF

### Converting Quote to Invoice

1. Open an accepted quotation
2. Click **Convert to Invoice**
3. System creates invoice with same line items
4. Review and send to customer

### Recording a Payment

1. Open an invoice
2. Click **Record Payment**
3. Enter amount, payment method, and optional note
4. Click **Save**
5. Invoice status updates automatically if fully paid
6. Generate receipt PDF if needed

### Managing Messages

1. **View Messages**: Click **Messages** in sidebar
   - Red badge shows unread count
   - Green dot indicates unread messages in list

2. **Read a Message**: Click **View** on any message
   - Automatically marks as read
   - Shows full message content and sender details

3. **Reply**: Click **Reply** button
   - Opens default email client with recipient pre-filled

4. **Manage Status**: Use **Mark Read** / **Mark Unread** buttons

5. **Delete**: Click trash icon (requires confirmation)

### Adding Products/Services

1. Navigate to **Products** → **Add Product**
2. Enter name, description, price, and type (Service/Product)
3. Click **Save Product**
4. Product now available for auto-fill in quotations and invoices

### Company Settings

1. Navigate to **Settings**
2. Update company information:
   - Company name
   - Logo (appears on PDFs)
   - Email, phone, address
   - Website URL
   - Tax/PIN number
3. Click **Save Settings**

---

## Development

### Running Migrations

When models change, update the database:

```bash
docker compose run --rm web python manage.py makemigrations
docker compose run --rm web python manage.py migrate
```

### Creating a Superuser

```bash
docker compose run --rm web python manage.py createsuperuser
```

### Accessing Django Shell

```bash
docker compose run --rm web python manage.py shell
```

### Running Tests

```bash
docker compose run --rm web python manage.py test
```

### Installing New Dependencies

1. Add package to `requirements.txt`
2. Rebuild container:
   ```bash
   docker compose build
   docker compose up -d
   ```

### Viewing Logs

```bash
# Real-time logs
docker compose logs -f

# Last 50 lines
docker compose logs --tail=50

# Specific service
docker compose logs web
```

### Stopping the Application

```bash
# Stop temporarily
docker compose down

# Stop and remove volumes (resets database)
docker compose down -v
```

---

## Project Structure

```
sysnet-ventures/
├── billing/                    # Main application module
│   ├── migrations/             # Database migrations
│   ├── models.py               # Data models (Customer, Invoice, etc.)
│   ├── views.py                # Request handlers
│   ├── forms.py                # Django forms
│   ├── urls.py                 # URL routing
│   ├── context_processors.py   # Template context (unread count, company info)
│   └── admin.py                # Django admin configuration
│
├── sysnet_core/                # Project settings module
│   ├── settings.py             # Django settings
│   ├── urls.py                 # Root URL configuration
│   └── wsgi.py                 # WSGI entry point
│
├── templates/                  # HTML templates
│   ├── base.html               # Base template for public pages
│   ├── home.html               # Landing page with contact form
│   └── billing/                # Dashboard templates
│       ├── base_dashboard.html # Dashboard layout with sidebar
│       ├── dashboard.html      # Dashboard overview
│       ├── message_list.html   # Messages inbox
│       ├── message_detail.html # Single message view
│       ├── product_list.html   # Product catalog
│       ├── product_form.html   # Add/edit product
│       ├── company_settings.html # Company profile settings
│       └── pdf_*.html          # PDF templates (invoice, quotation, receipt)
│
├── media/                      # User-uploaded files (logos, etc.)
├── static/                     # Static assets (collected by WhiteNoise)
├── docker-compose.yml          # Docker Compose configuration
├── Dockerfile                  # Container build instructions
├── requirements.txt            # Python dependencies
├── manage.py                   # Django management script
└── README.md                   # This file
```

---

## Security

### Best Practices Implemented

- **CSRF Protection** - All POST forms include CSRF tokens
- **Authentication Required** - All dashboard views require login
- **Password Hashing** - Django's built-in password hashing
- **SQL Injection Protection** - Django ORM parameterized queries
- **XSS Protection** - Automatic template escaping

### Recommendations for Production

1. **Change Default Password**
   ```bash
   docker compose run --rm web python manage.py changepassword admin
   ```

2. **Set Environment Variables**
   - `SECRET_KEY` - Use a strong, unique key
   - `DEBUG=False` - Disable debug mode
   - `ALLOWED_HOSTS` - Restrict to your domain

3. **Use HTTPS** - Configure SSL/TLS termination

4. **Database** - Migrate to PostgreSQL for production

5. **Regular Backups**
   ```bash
   # Backup database
   docker compose run --rm web cp /app/db.sqlite3 /backups/db-$(date +%Y%m%d).sqlite3
   ```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs web

# Rebuild
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Database Errors

```bash
# Run migrations
docker compose run --rm web python manage.py migrate

# If migrations fail, reset (WARNING: deletes data)
docker compose down -v
docker compose up -d
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
```

### Static Files Not Loading

```bash
# Collect static files
docker compose run --rm web python manage.py collectstatic --noinput
```

### PDF Generation Issues

- Ensure xhtml2pdf is installed: `pip install xhtml2pdf`
- Check that company logo path is accessible
- Verify CSS is inline-compatible (xhtml2pdf limitations)

### Contact Form Not Saving Messages

1. Check that migrations ran: `python manage.py showmigrations`
2. Verify ContactMessage model exists in admin
3. Check browser console for JavaScript errors

---

## Support

For issues, questions, or feature requests, please contact the development team.

---

## License

Proprietary - Sysnet Ventures. All rights reserved.

---

**Last Updated**: March 2026  
**Version**: 1.0.0
