# Sysnet Technologies — Business Platform

A complete, production-oriented corporate website **and** business management platform for
**Sysnet Technologies**, a Kenyan ICT solutions company. It combines a polished public website
with a full quotation → invoice → payment → receipt workflow, VAT-compliant Kenyan tax handling,
a self-service client portal, role-based staff access, and Docker deployment.

---

## Table of Contents
1. [Overview & Architecture](#overview--architecture)
2. [Feature Summary](#feature-summary)
3. [Technology Stack](#technology-stack)
4. [Quick Start (Docker)](#quick-start-docker)
5. [Creating the First Administrator](#creating-the-first-administrator)
6. [Environment Variables](#environment-variables)
7. [Database Migrations](#database-migrations)
8. [Backup & Restore](#backup--restore)
9. [Production Deployment (Ubuntu VPS)](#production-deployment-ubuntu-vps)
10. [Running Tests](#running-tests)
11. [Roles & Permissions](#roles--permissions)
12. [VAT & Tax Configuration](#vat--tax-configuration)
13. [Project Structure](#project-structure)
14. [Troubleshooting](#troubleshooting)
15. [Remaining Limitations](#remaining-limitations)

---

## Overview & Architecture

A single maintainable Django monolith with three logical apps:

```
                        ┌─────────────────────────────┐
  Public website  ────►  │  website   (home, services, │
  (no login needed)      │  products, portfolio, forms)│
                        └──────────┬──────────────────┘
                                   │
  Client portal    ─────►  ┌───────▼──────────┐     ┌──────────────┐
  (client role)            │  billing         │────►│ PostgreSQL   │
                           │  quotations      │     └──────────────┘
  Staff dashboard  ─────►  │  invoices        │     ┌──────────────┐
  (sales/finance/admin)    │  payments        │────►│ WhiteNoise   │
                           │  receipts        │     │ static files │
                           │  credit notes    │     └──────────────┘
                           │  CRM & reports   │     ┌──────────────┐
                           └───────┬──────────┘────►│ Media (logo, │
                                   │                │ evidence)    │
                           ┌───────▼──────────┐     └──────────────┘
                           │  accounts        │
                           │  users/roles,    │
                           │  audit, throttle │
                           └──────────────────┘
```

- **Authentication**: Django sessions; login throttled per username and IP (fail-closed).
- **Authorization**: enforced **server-side** by decorators on every view — hiding buttons in
  the UI is never the only guard.
- **Financial integrity**: all totals are computed server-side with `Decimal` (never floats);
  monetary rounding is `ROUND_HALF_UP` to 2 dp, documented in `billing/money.py`.
- **Immutability**: issued documents are never edited or deleted — they are voided or credited,
  and every sensitive action is written to an append-only audit log.
- **PDF documents** (quotation, invoice, receipt, statement, credit note data) render
  server-side via xhtml2pdf with shared branding.
- **Emails**: branded HTML + plain-text fallback, retry with delivery tracking
  (`NotificationLog`); a broken mail server never corrupts a financial transaction.

## Feature Summary

**Public website**
- Homepage with hero, featured services, why-us, industries, approved project showcase
- About (mission/vision/values/approach)
- 8 editable service pages (networking, fiber/GPON, computer sales & maintenance, software
  development, cloud & hosting, cybersecurity, managed IT, IT automation), each with an
  enquiry form
- Product catalogue (admin-curated; optional prices; enquiry workflow — no invented stock)
- Portfolio (only projects marked public)
- Contact form with category routing, WhatsApp link, phone
- Request-a-Quote form (staff notified; **no** auto-invoice)
- SEO: editable meta titles/descriptions, Open Graph, sitemap.xml, robots.txt, clean URLs
- Rate limiting on all public forms

**Business workflow**
- Client CRM (individual/business, KRA PIN, VAT details, addresses, status, notes)
- Catalog with SKU, unit, tax category defaults, stock tracking, archiving
- Quotations: dynamic line builder, VAT-exclusive **and** VAT-inclusive pricing, per-line
  discounts, mixed tax categories, notes/terms/validity, draft → send → client accepts/
  rejects/requests changes → revise (revisions preserved) → convert to invoice
- Invoices: unique numbers, issue/void/credit notes, payment instructions, automatic
  outstanding-balance calculation, overdue tracking
- Payments: staff-recorded and client-submitted (with proof-of-evidence upload, securely
  stored and permission-checked); M-Pesa / bank / cash / card / cheque / other; duplicate
  transaction references rejected; verification workflow; **client submissions never mark
  an invoice paid by themselves**
- Receipts: auto-issued only on confirmation; unique numbers; branded PDF; idempotent
- Allocations: one payment across multiple invoices; cannot exceed payment remainder or
  invoice balance; correctable (deallocate)
- Account statements per client (screen + PDF) and CSV exports

**Client portal** — dashboard with balances, document downloads, accept/reject quotations,
payment reference submission with status tracking, statements, profile editing, support
requests. Mobile-first and strictly scoped to the logged-in client's own data.

**Staff dashboard** — real figures only (revenue received, invoiced, outstanding, overdue,
pending quotations, accepted quotations, payments awaiting verification, unallocated
payments, monthly revenue chart, invoice aging buckets, recent activity).

**Administration** — company settings (identity, logo upload, KRA PIN/VAT, numbering
prefixes, default terms, payment instructions, brand colors), configurable effective-dated
tax categories, user management, audit log.

## Technology Stack

| Component      | Choice                                   |
|----------------|------------------------------------------|
| Backend        | Python 3.11, Django 5.2                  |
| Database       | PostgreSQL 16 (SQLite only as a dev fallback without Docker) |
| Frontend       | Django templates, Tailwind-free custom CSS design system, vanilla JS |
| PDF            | xhtml2pdf (server-side)                  |
| Static files   | WhiteNoise (compressed, manifest)        |
| Auth           | Django sessions + role model + throttle backend |
| Web serving    | Gunicorn behind Nginx (production)       |
| Deployment     | Docker + Docker Compose                  |
| Tests          | Django test suite (`manage.py test`)     |

## Quick Start (Docker)

Prerequisites: **Docker 20.10+** and **Docker Compose 2.0+** — nothing else is installed on
the host.

```bash
# 1. Clone and configure
git clone <repository-url> && cd sysnet-ventures
cp .env.example .env
#    edit .env — set SECRET_KEY, POSTGRES_PASSWORD (and optionally the
#    DJANGO_SUPERUSER_* variables to get an admin created on first boot)

# 2. Start everything (Postgres + app)
docker compose up -d

# 3. Watch first boot (migrations run automatically; safe defaults seeded)
docker compose logs -f web

# 4. Open the site
#    Public website:  http://localhost:8000/
#    Staff dashboard: http://localhost:8000/billing/
#    Client portal:   http://localhost:8000/accounts/login/
#    Django admin:    http://localhost:8000/admin/
```

Stop with `docker compose down` (data persists in named volumes). `docker compose down -v`
**destroys** the database.

## Creating the First Administrator

**Option A — automatic (recommended):** set in `.env` before first boot:

```
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=your-strong-password
DJANGO_SUPERUSER_EMAIL=you@example.com
```

**Option B — interactive:**

```bash
docker compose run --rm web python manage.py createsuperuser
```

The superuser has the **Super Admin** role and sees the Administration menu
(company settings, tax categories, users, audit log). Create Finance / Sales / Client users
from **Dashboard → Users**. For Client users you must also create the matching Client record
and link it on the user form.

## Environment Variables

All configuration is environment-driven — no secrets in the image. See
[`.env.example`](.env.example) for the full annotated list. The essentials:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret — **required**, generate a random string |
| `DEBUG` | `True` only for local dev |
| `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` | your domain(s) |
| `POSTGRES_PASSWORD` | password for the bundled Postgres |
| `DATABASE_URL` | override to use an external/managed Postgres |
| `DJANGO_SUPERUSER_USERNAME/PASSWORD/EMAIL` | optional first-boot admin |
| `EMAIL_BACKEND`, `EMAIL_HOST*`, `DEFAULT_FROM_EMAIL`, `STAFF_NOTIFY_EMAIL` | outbound email |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS` | production HTTPS hardening (set by `docker-compose.prod.yml`) |
| `THROTTLE_LOGIN_LIMIT` / `THROTTLE_FORM_LIMIT` | rate-limit tuning |

## Database Migrations

Migrations run automatically on container start. To run them manually:

```bash
docker compose run --rm web python manage.py migrate
# after model changes (development):
docker compose run --rm web python manage.py makemigrations
```

## Backup & Restore

```bash
# Backup (Postgres dump + media tarball into ./backups/)
./scripts/backup.sh

# Restore
./scripts/restore.sh backups/db-<stamp>.dump backups/media-<stamp>.tar.gz
```

Automate the backup with cron, e.g. nightly at 02:00:
```
0 2 * * * cd /opt/sysnet && ./scripts/backup.sh /var/backups/sysnet
```

## Production Deployment (Ubuntu VPS)

1. **Install Docker**: `curl -fsSL https://get.docker.com | sh`
2. **Copy the project** to e.g. `/opt/sysnet` and create `.env` with production values:
   `DEBUG=False`, real `SECRET_KEY`, your domain in `ALLOWED_HOSTS` and
   `CSRF_TRUSTED_ORIGINS` (`https://yourdomain.com`), strong `POSTGRES_PASSWORD`, SMTP
   credentials.
3. **Start in production mode:**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```
   This enables the Nginx reverse proxy, security headers, secure cookies, and keeps
   Postgres private on the internal network (no published ports).
4. **DNS**: point your domain's A record at the VPS IP. The site is then reachable on
   `http://yourdomain.com`.
5. **HTTPS (Let's Encrypt)** — the included Nginx config is TLS-ready. Simplest robust
   setup: run [Caddy](https://caddyserver.com) or `certbot --nginx` on the host, or add a
   certificate at `deploy/certs/fullchain.pem` + `privkey.pem` and uncomment the 443
   listener in `deploy/nginx.conf`. Then set:
   ```
   CSRF_TRUSTED_ORIGINS=https://yourdomain.com
   SECURE_SSL_REDIRECT=True
   ```
6. **Firewall**: allow only 80/443 (and SSH). Postgres and the app are internal-only.
7. **Backups**: schedule `scripts/backup.sh` (see above).
8. **Updates**: `git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml build && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`

Volumes (`pg_data`, `media_data`) persist across restarts and rebuilds.

## Deploying to Render

Render runs this repo as-is (Docker runtime). The gunicorn entrypoint already binds
`0.0.0.0:$PORT`, which is what Render expects.

**Where `ALLOWED_HOSTS` goes:** Render Dashboard → your web service → **Environment** →
add/edit the `ALLOWED_HOSTS` variable. Set it to your Render hostname plus any custom
domain, comma-separated:

```
ALLOWED_HOSTS=sysnet.onrender.com,www.yourdomain.co.ke
CSRF_TRUSTED_ORIGINS=https://sysnet.onrender.com,https://www.yourdomain.co.ke
```

No code changes are needed — `sysnet_core/settings.py` reads it straight from the
environment. Restart the service after changing env vars.

**One-click option:** commit the included `render.yaml` blueprint, then in Render
**New → Blueprint** and pick the repo. It provisions the web service, a persistent disk
for uploaded media (`/app/media`), a Postgres instance wired into `DATABASE_URL`, and the
production security flags (`SECURE_SSL_REDIRECT`, secure cookies). You still fill in:

- `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` (your hostname)
- `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` (creates the first admin on boot)
- SMTP vars if you want real email delivery

Render terminates TLS, so keep `SECURE_SSL_REDIRECT=True` and leave
`SECURE_PROXY_SSL_HEADER` as configured — Django already trusts Render's
`X-Forwarded-Proto` header.

## Running Tests

```bash
# inside Docker (recommended)
docker compose run --rm web python manage.py test

# or locally in a venv
python -m manage test
```

The suite (36 tests) covers: VAT-inclusive/exclusive/mixed/zero-rated/discount/rounding
math, quotation→invoice→payment→receipt workflow, partial payments and balance tracking,
duplicate-reference rejection, allocation limits, unverified-payment isolation, client
submission safety, IDOR/cross-client access prevention, role enforcement, login
throttling, PDF generation, email-failure resilience, and audit logging.

Demo data for **development only** (refuses to run with `DEBUG=False`):
```bash
docker compose run --rm web python manage.py seed_demo
```

## Roles & Permissions

| Role | Access |
|---|---|
| **Super Admin** | Everything: settings, tax configuration, users, audit log |
| **Finance** | Invoices, payments, receipts, credit notes, quotations, reports |
| **Sales** | Clients, catalog, enquiries, quotations (no invoicing) |
| **Client** | Portal only — strictly their own quotations, invoices, payments, receipts, statement |

Permissions are enforced server-side (`billing/access.py` decorators). Access by a client
user to another client's document returns **403** and is test-covered.

## VAT & Tax Configuration

- Tax categories are **configurable and effective-dated** (Settings → Tax categories).
- Standard defaults seeded: Standard rated 16%, Zero rated, Exempt, Out of scope —
  clearly distinguished on documents and reports.
- Each document line **snapshots** its rate and category at creation; later tax changes
  never alter issued documents.
- Both VAT-exclusive and VAT-inclusive pricing are supported per line, with mixed
  categories in one document and a grouped VAT summary on invoices.
- ⚠ **Tax settings must be validated against current KRA requirements and the business's
  actual tax status** before issuing VAT documents. The platform provides correct
  arithmetic and configuration, not tax advice.

## Project Structure

```
├── accounts/            # Custom user model, roles, audit log, login throttling
├── billing/             # Domain: clients, catalog, documents, payments, VAT engine
│   ├── models.py        #   (all models incl. website content models)
│   ├── services.py      #   transactional business logic (the accounting rules)
│   ├── money.py         #   documented money/rounding policy
│   ├── views_staff.py / views_documents.py / views_portal.py
│   ├── document_forms.py / forms.py / validators.py
│   └── management/commands/  # seed_defaults (prod-safe), seed_demo (dev-only)
├── website/             # Public website views/urls
├── sysnet_core/         # Settings, root urls, sitemap, health check
├── templates/           # website/, billing/ (dashboard+PDFs), billing/portal/, emails/
├── static/              # css/app.css design system, js/app.js
├── deploy/              # nginx.conf (+ TLS cert location)
├── scripts/             # backup.sh, restore.sh
├── docker-compose.yml   # dev: web + postgres
├── docker-compose.prod.yml  # production overrides (+ nginx, hardening)
└── Dockerfile           # non-root, health-checked image
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| **Site unreachable after a successful build** | Usually one of: (1) you started the **prod** profile and nothing listens on your port — prod publishes **80/443 via nginx** (port 8000 is not published); (2) nginx crash-looped on a bad/missing config — `docker compose logs nginx`; (3) web is unhealthy — `docker compose logs web`. Verify with `docker compose ps` and `curl -I http://localhost/healthz`. |
| `web` exits with "Database did not become ready" | Postgres not up yet — `docker compose logs db`; the entrypoint retries 30×/2s |
| `FATAL: password authentication failed for user "sysnet"` | The Postgres volume was initialized with a **different** `POSTGRES_PASSWORD` than the one now in `.env` (env vars set at first boot win). Either restore the old password in `.env`, or wipe the volume: `docker compose down -v && docker compose up -d` (destroys data). |
| Static files look unstyled after update | `docker compose run --rm web python manage.py collectstatic` (runs automatically on boot) |
| `502` from nginx | App still starting or crashed — `docker compose logs web` |
| Uploaded logo 404s in production | Media is served by Django with permission checks (payment evidence is staff-only). Ensure `media_data` volume exists and the file was uploaded via **Settings → Company**. |
| Emails not arriving | Dev default prints to container logs; set SMTP vars for real delivery; check **Dashboard → notification status** via `NotificationLog` admin |
| Forgot admin password | `docker compose run --rm web python manage.py reset_admin_password <username> <newpass>` |
| Reset everything (destroys data!) | `docker compose down -v && docker compose up -d` |

## Remaining Limitations

- **M-Pesa Daraja (STK Push / callbacks)**: architecture is ready (Payment model,
  verification workflow, idempotent references, env-based credentials pattern), but no
  live integration is enabled. Manual M-Pesa recording + verification is fully functional.
  Never make live Daraja calls without proper credentials and authorization.
- **Two-factor authentication**: session security, throttling and activation controls are
  in place; a TOTP second factor can be added on top of the accounts app.
- **Background jobs (Celery/Redis)**: not required at current scale — emails retry inline
  with delivery logging. Add a worker when volume justifies it.
- **Testimonials**: the model exists but the homepage shows them only when real approved
  content is supplied (none is invented).
- **VAT settings** must be verified against current KRA rules by the business.

---

*Proprietary — Sysnet Technologies. All rights reserved.*
