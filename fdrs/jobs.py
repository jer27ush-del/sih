"""Daily background jobs (Section 9.8). Every step checks state before acting, and every
reminder is recorded in ReminderLog, so re-running the job never repeats an alert."""
from collections import Counter
from datetime import timedelta

from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from notifications.models import ReminderLog
from notifications.services import administrators, institution_users, notify, officers
from portal.models import SystemSettings

from .maturity import days_to_maturity, reminder_window
from .models import FDR, FdrRequest, Query
from .services import lock_fdr
from .workflow import change_status

S = FDR.Status


def _send_once(key, kind, recipients, message, link, fdr=None):
    with transaction.atomic():
        _, created = ReminderLog.objects.get_or_create(key=key, defaults={"kind": kind, "fdr": fdr})
        if not created:
            return False
        notify(recipients, type=kind, message=message, link=link)
    return True


def run_daily_jobs(today=None):
    today = today or timezone.localdate()
    cfg = SystemSettings.load()
    thresholds = sorted(set(cfg.maturity_thresholds))
    summary = Counter()

    # 1. Maturity status: Active -> Nearing Maturity -> Matured (never released automatically).
    for pk in list(FDR.objects.filter(status__in=[S.ACTIVE, S.NEARING_MATURITY]).values_list("pk", flat=True)):
        with transaction.atomic():
            fdr = lock_fdr(pk)
            days = days_to_maturity(fdr.maturity_date, today)
            if fdr.status == S.ACTIVE and reminder_window(days, thresholds) is not None:
                change_status(fdr, S.NEARING_MATURITY, None, note="Entered the reminder window")
                summary["moved_to_nearing"] += 1
            if fdr.status == S.NEARING_MATURITY and days <= 0:
                change_status(fdr, S.MATURED, None, note="Maturity date reached")
                summary["moved_to_matured"] += 1

    # 2. Maturity reminders: one per reminder window, plus one on the maturity date.
    for fdr in FDR.objects.filter(status__in=[S.NEARING_MATURITY, S.MATURED]).select_related("institution"):
        days = days_to_maturity(fdr.maturity_date, today)
        window = reminder_window(days, thresholds)
        if days <= 0:
            key, label = f"maturity-day:{fdr.pk}", "the maturity date has been reached"
        elif window is not None:
            key, label = f"maturity:{fdr.pk}:{window}", f"{days} days remain before maturity"
        else:
            continue
        message = f"{fdr.fdr_number}: {label}. Submit a renewal or release request."
        recipients = institution_users(fdr.institution_id) + officers()
        if _send_once(key, "maturity", recipients, message, f"/fdrs/{fdr.pk}", fdr):
            summary["maturity_reminders"] += 1

    # 3. Overdue escalation: matured, with no renewal or release request after the set period.
    cutoff = today - timedelta(days=cfg.overdue_escalation_days)
    overdue = FDR.objects.filter(status=S.MATURED, maturity_date__lte=cutoff).exclude(
        requests__status__in=FdrRequest.OPEN_STATUSES
    )
    for fdr in overdue:
        message = f"{fdr.fdr_number} matured on {fdr.maturity_date:%d %b %Y} with no action taken."
        if _send_once(f"overdue:{fdr.pk}", "overdue", administrators(), message, f"/fdrs/{fdr.pk}", fdr):
            summary["overdue_escalations"] += 1
            for contact in cfg.escalation_contacts:  # configured escalation addresses (not user accounts)
                send_mail("AICTE FDR overdue escalation", message, settings.DEFAULT_FROM_EMAIL, [contact],
                          fail_silently=True)

    # 4. Query follow-up: queries unanswered beyond the set period.
    cutoff_time = timezone.now() - timedelta(days=cfg.query_followup_days)
    for query in Query.objects.filter(status=Query.Status.OPEN, raised_at__lte=cutoff_time).select_related("fdr"):
        message = f"A query on {query.fdr.fdr_number} is still waiting for your reply."
        if _send_once(f"query:{query.pk}", "query_followup", institution_users(query.fdr.institution_id),
                      message, f"/fdrs/{query.fdr_id}", query.fdr):
            summary["query_followups"] += 1

    return dict(summary)
