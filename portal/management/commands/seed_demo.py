from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from audit.services import record_audit
from fdrs.models import FDR
from institutions.models import Institution
from portal.models import SystemSettings

DEMO_PASSWORD = "demo123"  # for local development ONLY; the same password the frontend demo uses

INSTITUTIONS = [
    {"code": "DEMO001", "name": "Demo Engineering College", "state": "Tamil Nadu", "contact_name": "Priya Sample",
     "email": "demo@example.com", "phone": "+91 90000 10001", "status": "Active"},
    {"code": "DEMO002", "name": "Sample Institute of Technology", "state": "Karnataka", "contact_name": "Arun Demo",
     "email": "sample@example.com", "phone": "+91 90000 10002", "status": "Active"},
    {"code": "DEMO003", "name": "Fictional Polytechnic College", "state": "Telangana", "contact_name": "Meera Example",
     "email": "poly@example.com", "phone": "+91 90000 10003", "status": "Inactive"},
]

USERS = [
    ("institution@demo.test", "Demo Institution User", "institution_user", "DEMO001"),
    ("officer@demo.test", "Sample Scrutiny Officer", "scrutiny_officer", None),
    ("admin@demo.test", "Demo Administrator", "administrator", None),
    ("auditor@demo.test", "Sample Auditor", "auditor", None),
]


class Command(BaseCommand):
    help = "Create demo institutions, the four demo accounts (password demo123) and sample FDRs. Development only."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true",
                            help="Allow running when DJANGO_DEBUG is off. Never use on a production database.")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to create demo accounts with DEBUG off. Use --force only on a non-production database.")

        with transaction.atomic():
            SystemSettings.load()
            institutions = {}
            for data in INSTITUTIONS:
                inst, _ = Institution.objects.update_or_create(code=data["code"], defaults=data)
                institutions[data["code"]] = inst

            users = {}
            for email, name, role, code in USERS:
                institution = institutions[code] if code else None
                user, _ = User.objects.update_or_create(
                    email=email,
                    defaults={"name": name, "role": role, "institution": institution, "is_active": True},
                )
                user.set_password(DEMO_PASSWORD)
                user.save()
                users[email] = user

            admin = users["admin@demo.test"]
            samples = [
                ("DEMO001", "DEMO-FDR-1001", "Sample National Bank", "Chennai Main", 50000000, "2026-01-15",
                 "2027-01-15", "6.50", "cumulative", "Security Deposit", FDR.Status.ACTIVE, False),
                ("DEMO002", "DEMO-FDR-1002", "Demo State Bank", "Bengaluru Central", 25000000, "2025-08-01",
                 "2026-11-15", "6.25", "periodic", "Security Deposit", FDR.Status.UNDER_VERIFICATION, True),
                ("DEMO001", "DEMO-FDR-1003", "Sample National Bank", "Adambakkam", 12500000, "2024-12-01",
                 "2026-12-01", "6.75", "cumulative", "Performance Guarantee", FDR.Status.NEARING_MATURITY, False),
            ]
            created = []
            for code, number, bank, branch, paise, issue, maturity, rate, payout, category, status, flag in samples:
                if FDR.objects.filter(fdr_number=number, bank=bank).exists():
                    continue
                fdr = FDR.objects.create(
                    institution=institutions[code], fdr_number=number, bank=bank, branch=branch,
                    amount_paise=paise, issue_date=issue, maturity_date=maturity, interest_rate=rate,
                    payout_type=payout, category=category, status=status, review_flag=flag, submitted_by=admin,
                    lien_marked=True,
                )
                created.append(fdr.fdr_number)
            record_audit(action="seed.demo_data", entity="Seed", entity_id="demo", actor=admin,
                         new={"fdrs_created": created})

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready. Password for every demo account: {DEMO_PASSWORD}. FDRs created: {created or 'none (already present)'}"
        ))
