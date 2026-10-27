"""Maturity reminder rules, sending, retries and idempotency.

Rules (see README, "Maturity reminders"):
- A reminder is due on the exact day an FDR is 90, 60 or 30 calendar days from maturity.
- Only FDRs in an active maturity-cycle status receive reminders (Active, Nearing Maturity).
- Each reminder goes to the institution's contact email address.
- A successful send is recorded once; repeated runs never send it again.
- Failed sends are retried on later runs, up to MAX_ATTEMPTS.
"""
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from audit.services import record_audit
from fdrs.models import FDR

from .models import MAX_ATTEMPTS, REMINDER_DAYS, ReminderDelivery

logger = logging.getLogger(__name__)
ELIGIBLE_STATUSES = [FDR.Status.ACTIVE, FDR.Status.NEARING_MATURITY]


@dataclass
class RunSummary:
    run_date: date
    dry_run: bool
    counts: Counter = field(default_factory=Counter)

    def add(self, key):
        self.counts[key] += 1


def recipient_for(fdr):
    """The institution's contact address, or '' if it is missing or invalid."""
    email = (fdr.institution.email or "").strip()
    try:
        validate_email(email)
    except ValidationError:
        return ""
    return email


def _safe_error(exc):
    """Short error text without passwords or server credentials."""
    text = f"{exc.__class__.__name__}: {exc}"
    password = getattr(settings, "EMAIL_HOST_PASSWORD", "")
    if password:
        text = text.replace(password, "[redacted]")
    return " ".join(text.split())[:300]


def _send(fdr, days_remaining, recipient):
    context = {
        "institution_name": fdr.institution.name,
        "fdr_number": fdr.fdr_number,
        "bank": fdr.bank,
        "branch": fdr.branch,
        "maturity_date": fdr.maturity_date,
        "days_remaining": days_remaining,
        "status": fdr.status,
        "portal_url": settings.PORTAL_BASE_URL,
    }
    subject = f"FDR Maturity Reminder — {fdr.fdr_number} — {days_remaining} Days"
    text_body = render_to_string("reminders/email/reminder.txt", context)
    html_body = render_to_string("reminders/email/reminder.html", context)
    message = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [recipient])
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)


def _process(fdr, reminder_days, run_date, dry_run, summary):
    """Send (or record) one reminder event. Safe to call repeatedly for the same event."""
    days_remaining = (fdr.maturity_date - run_date).days
    recipient = recipient_for(fdr)

    if dry_run:
        done = ReminderDelivery.objects.filter(
            fdr=fdr, reminder_days=reminder_days, maturity_date=fdr.maturity_date,
            status=ReminderDelivery.Status.ACCEPTED,
        ).exists()
        if done:
            summary.add("already_sent")
        elif recipient:
            summary.add("would_send")
        else:
            summary.add("would_skip_no_recipient")
        return

    with transaction.atomic():
        delivery, _ = ReminderDelivery.objects.get_or_create(
            fdr=fdr, reminder_days=reminder_days, maturity_date=fdr.maturity_date,
            defaults={"status": ReminderDelivery.Status.FAILED, "recipient": recipient},
        )
        # Lock the row so two overlapping runs cannot both send the same reminder.
        delivery = ReminderDelivery.objects.select_for_update().get(pk=delivery.pk)

        if delivery.status == ReminderDelivery.Status.ACCEPTED:
            summary.add("already_sent")
            return
        if delivery.attempts >= MAX_ATTEMPTS:
            summary.add("gave_up")
            return

        delivery.recipient = recipient
        if not recipient:
            delivery.status = ReminderDelivery.Status.SKIPPED
            delivery.last_error = "The institution record has no valid contact email address."
            delivery.save()
            summary.add("skipped")
            return

        try:
            _send(fdr, days_remaining, recipient)
        except Exception as exc:  # noqa: BLE001 - any SMTP/transport error is recorded, not raised
            delivery.status = ReminderDelivery.Status.FAILED
            delivery.attempts += 1
            delivery.last_error = _safe_error(exc)
            delivery.save()
            summary.add("failed")
            logger.warning("Reminder failed for %s: %s", fdr.fdr_number, delivery.last_error)
            return

        delivery.status = ReminderDelivery.Status.ACCEPTED
        delivery.attempts += 1
        delivery.last_error = ""
        delivery.accepted_at = timezone.now()
        delivery.save()
        record_audit(action="reminder.accepted", entity="FDR", entity_id=fdr.pk,
                     new={"reminder_days": reminder_days, "recipient": recipient})
        summary.add("accepted")


def run_reminders(run_date=None, *, dry_run=False):
    """Process every reminder due on `run_date` (default: today in Asia/Kolkata), plus retries."""
    run_date = run_date or timezone.localdate()
    summary = RunSummary(run_date=run_date, dry_run=dry_run)

    handled = set()  # (fdr id, interval) pairs already processed in this run
    for reminder_days in REMINDER_DAYS:
        due_on = run_date + timedelta(days=reminder_days)
        fdrs = FDR.objects.filter(status__in=ELIGIBLE_STATUSES, maturity_date=due_on).select_related("institution")
        for fdr in fdrs:
            summary.add("due")
            handled.add((fdr.pk, reminder_days))
            _process(fdr, reminder_days, run_date, dry_run, summary)

    # Retry earlier failures and skipped records (for example, after an institution adds its email).
    retries = ReminderDelivery.objects.filter(
        status__in=[ReminderDelivery.Status.FAILED, ReminderDelivery.Status.SKIPPED],
        maturity_date__gte=run_date,
        fdr__status__in=ELIGIBLE_STATUSES,
    ).select_related("fdr__institution")
    for delivery in retries:
        if delivery.fdr.maturity_date != delivery.maturity_date:
            continue  # the maturity date changed; the new date gets its own reminders
        if (delivery.fdr_id, delivery.reminder_days) in handled:
            continue  # already attempted in this run
        handled.add((delivery.fdr_id, delivery.reminder_days))
        summary.add("retry_candidates")
        _process(delivery.fdr, delivery.reminder_days, run_date, dry_run, summary)

    return summary
