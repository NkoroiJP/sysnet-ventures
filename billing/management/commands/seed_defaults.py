"""Seed safe production defaults: company settings, tax categories, service pages.

Contains NO fake clients, transactions, testimonials or financial records —
safe to run in production. Demo data lives in seed_demo (dev only).
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from billing.models import CompanySettings, seed_tax_categories, ServicePage

SERVICES = [
    {
        'slug': 'enterprise-networking',
        'title': 'Enterprise Networking & Infrastructure',
        'icon': 'fa-network-wired',
        'summary': 'Structured cabling, switching, routing and Wi-Fi infrastructure designed for reliability and growth.',
        'description': (
            'We design, supply and implement enterprise network infrastructure for offices, campuses and '
            'institutions — from structured cabling and server racks to managed switching, routing and '
            'enterprise Wi-Fi. Every deployment is documented, tested and handed over with as-built diagrams.'
        ),
        'problems': [
            'Unreliable Wi-Fi and dead zones across the office',
            'Ad-hoc cabling that fails audits and complicates troubleshooting',
            'Network outages that halt business operations',
            'No documentation or visibility of the existing network',
        ],
        'deliverables': [
            'Site survey and network design documentation',
            'Structured cabling and patching certified to standard',
            'Switching, routing and VLAN configuration',
            'Enterprise Wi-Fi with seamless roaming',
            'As-built diagrams and administrator training',
        ],
        'sort_order': 1,
    },
    {
        'slug': 'fiber-gpon',
        'title': 'Fiber Optics & GPON Solutions',
        'icon': 'fa-bolt',
        'summary': 'Fiber backbone design, splicing, OTDR testing and GPON deployments for campuses and ISPs.',
        'description': (
            'From fiber backbone installations to full GPON (Gigabit Passive Optical Network) deployments, '
            'we deliver carrier-grade fiber solutions: route planning, ducting, splicing, termination, '
            'OTDR/FLuke testing and documentation for campuses, residential estates and service providers.'
        ),
        'problems': [
            'Copper links that cannot carry modern bandwidth demands',
            'Inter-building connectivity that degrades in bad weather',
            'Slow, unreliable internet distribution across large premises',
        ],
        'deliverables': [
            'Fiber route survey and Bill of Quantities',
            'Ducting, cable pulling and professional splicing',
            'OTDR and power-meter certification reports',
            'GPON OLT/ONU deployment and subscriber provisioning',
        ],
        'sort_order': 2,
    },
    {
        'slug': 'computer-sales-maintenance',
        'title': 'Computer Sales, Repair & Maintenance',
        'icon': 'fa-laptop',
        'summary': 'Quality computers and accessories with professional repair and preventive maintenance plans.',
        'description': (
            'We supply genuine computers, laptops, printers and accessories, backed by workshop-grade repair '
            'services and structured maintenance contracts that keep your fleet healthy and productive.'
        ),
        'problems': [
            'Aging machines that slow staff down',
            'Recurring hardware failures with no vendor accountability',
            'No asset register or preventive maintenance schedule',
        ],
        'deliverables': [
            'Hardware sourcing and procurement advisory',
            'Diagnostics, repair and component replacement',
            'Preventive maintenance schedules and reports',
            'Asset register and warranty tracking',
        ],
        'sort_order': 3,
    },
    {
        'slug': 'software-development',
        'title': 'Software Development & Business Systems',
        'icon': 'fa-code',
        'summary': 'Custom web applications, ERPs and integrations built around your exact workflows.',
        'description': (
            'Our engineering team designs and builds business systems — web applications, customer portals, '
            'ERP/CRM implementations and third-party integrations — delivered with documentation, training '
            'and ongoing support.'
        ),
        'problems': [
            'Manual spreadsheets that cannot scale or audit',
            'Off-the-shelf software that does not fit your workflow',
            'Disconnected systems with duplicate data entry',
        ],
        'deliverables': [
            'Requirements workshops and system specification',
            'Custom web/mobile application development',
            'Integration with M-Pesa, ERP, accounting and other APIs',
            'User training, documentation and support retainer',
        ],
        'sort_order': 4,
    },
    {
        'slug': 'cloud-hosting',
        'title': 'Cloud Computing & Hosting',
        'icon': 'fa-cloud',
        'summary': 'Cloud migration, hosted email, websites and application hosting with local support.',
        'description': (
            'We help businesses move to the cloud safely — hosted email, cloud backups, website and '
            'application hosting, and hybrid setups — with transparent pricing and a local team on call.'
        ),
        'problems': [
            'On-premise servers that are costly to power and maintain',
            'Data loss risk with no reliable backups',
            'Website and email downtime harming the brand',
        ],
        'deliverables': [
            'Cloud readiness assessment and migration plan',
            'Hosted email and collaboration setup',
            'Managed cloud backups with restore testing',
            'Application hosting, monitoring and support',
        ],
        'sort_order': 5,
    },
    {
        'slug': 'cybersecurity',
        'title': 'Cybersecurity',
        'icon': 'fa-shield-halved',
        'summary': 'Security assessments, firewalls, endpoint protection and staff awareness training.',
        'description': (
            'We protect businesses against evolving threats with security assessments, next-generation '
            'firewalls, endpoint protection, email security and practical staff awareness training.'
        ),
        'problems': [
            'Ransomware and phishing attacks disrupting operations',
            'Unmanaged devices and weak access controls',
            'No incident response plan when things go wrong',
        ],
        'deliverables': [
            'Vulnerability assessment and remediation plan',
            'Firewall deployment and configuration hardening',
            'Endpoint and email protection rollout',
            'Staff security-awareness training',
        ],
        'sort_order': 6,
    },
    {
        'slug': 'managed-it',
        'title': 'Managed IT Services',
        'icon': 'fa-headset',
        'summary': 'Outsource your IT department — helpdesk, monitoring and vendor management for a fixed fee.',
        'description': (
            'Our managed IT plans give you a full IT department on subscription: helpdesk support, proactive '
            'monitoring, patching, asset management and vendor coordination under a clear SLA.'
        ),
        'problems': [
            'No reliable IT person when systems fail',
            'Firefighting instead of proactive maintenance',
            'Multiple vendors with no single point of accountability',
        ],
        'deliverables': [
            'Dedicated helpdesk with ticket tracking',
            'Proactive monitoring, patching and backups',
            'SLA-backed response and resolution times',
            'Monthly reporting and IT budgeting advice',
        ],
        'sort_order': 7,
    },
    {
        'slug': 'it-automation',
        'title': 'IT Automation & Systems Integration',
        'icon': 'fa-gears',
        'summary': 'Automate repetitive workflows and connect your systems so data flows without manual work.',
        'description': (
            'We automate repetitive business processes and integrate the systems you already use — from '
            'report generation and notifications to full workflow orchestration across departments.'
        ),
        'problems': [
            'Staff spending hours on manual data entry and reports',
            'Systems that do not talk to each other',
            'Error-prone handoffs between departments',
        ],
        'deliverables': [
            'Workflow assessment and automation roadmap',
            'Integration development between business systems',
            'Automated reporting, alerts and approvals',
            'Documentation and knowledge transfer',
        ],
        'sort_order': 8,
    },
]


class Command(BaseCommand):
    help = 'Seed safe defaults: company settings, tax categories and service pages (idempotent, production-safe).'

    @transaction.atomic
    def handle(self, *args, **options):
        settings_obj = CompanySettings.load()
        seed_tax_categories()

        created_pages = 0
        for spec in SERVICES:
            page, created = ServicePage.objects.get_or_create(slug=spec['slug'], defaults=spec)
            if created:
                created_pages += 1

        self.stdout.write(self.style.SUCCESS(
            f'Company settings ready ({settings_obj.name}); tax categories ensured; '
            f'{created_pages} service page(s) created.'
        ))
