from django.core.management.base import BaseCommand

from fdrs.jobs import run_daily_jobs


class Command(BaseCommand):
    help = "Run the daily maturity, reminder, escalation and query follow-up jobs. Safe to re-run."

    def handle(self, *args, **options):
        summary = run_daily_jobs()
        self.stdout.write(self.style.SUCCESS(f"Daily jobs finished. Actions taken: {summary or 'none due'}"))
