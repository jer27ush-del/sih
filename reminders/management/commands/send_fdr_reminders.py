"""Send 90/60/30-day FDR maturity reminders.

Examples:
  python manage.py send_fdr_reminders                       # today (Asia/Kolkata)
  python manage.py send_fdr_reminders --date 2026-10-27     # calculate as if it were that day
  python manage.py send_fdr_reminders --date 2026-10-27 --dry-run   # report only, send nothing
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from reminders.services import run_reminders


class Command(BaseCommand):
    help = "Send FDR maturity reminders due 90, 60 and 30 days before maturity. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Run as of this date (YYYY-MM-DD). Defaults to today.")
        parser.add_argument("--dry-run", action="store_true", help="Show what would happen; send nothing and record nothing.")

    def handle(self, *args, **options):
        try:
            run_date = date.fromisoformat(options["date"]) if options["date"] else None
        except ValueError as exc:
            raise CommandError("--date must be in YYYY-MM-DD format.") from exc

        summary = run_reminders(run_date, dry_run=options["dry_run"])
        counts = summary.counts
        mode = "DRY RUN (nothing sent or recorded)" if summary.dry_run else "LIVE"
        self.stdout.write(f"Maturity reminders as of {summary.run_date:%d %b %Y} — {mode}")
        self.stdout.write(f"  Due today (90/60/30-day windows): {counts['due']}")
        if summary.dry_run:
            self.stdout.write(f"  Would send:                        {counts['would_send']}")
            self.stdout.write(f"  Would skip (no valid email):       {counts['would_skip_no_recipient']}")
        else:
            self.stdout.write(f"  Accepted by mail server:           {counts['accepted']}")
            self.stdout.write(f"  Failed (will retry on a later run): {counts['failed']}")
            self.stdout.write(f"  Skipped (no valid email):          {counts['skipped']}")
        self.stdout.write(f"  Already sent earlier (no action):  {counts['already_sent']}")
        if counts["retry_candidates"]:
            self.stdout.write(f"  Earlier failures/skips checked:    {counts['retry_candidates']}")
        if counts["gave_up"]:
            self.stdout.write(self.style.WARNING(f"  Stopped after max attempts:        {counts['gave_up']} (needs attention)"))
