"""Tests for maturity reminders. They use Django's in-memory test mail backend, so no real email is sent."""
from datetime import date, timedelta
from io import StringIO
from smtplib import SMTPException
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from fdrs.models import FDR
from institutions.models import Institution

from .models import ReminderDelivery
from .services import run_reminders

RUN_DATE = date(2026, 10, 27)


class ReminderTestBase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email="admin@t.test", password="Correct-horse-battery-9",
                                              name="Admin", role="administrator")
        self.inst_a = self.make_institution("RA01", "a-college@example.test")
        self.inst_b = self.make_institution("RB02", "b-college@example.test")
        self.counter = 0

    def make_institution(self, code, email):
        return Institution.objects.create(code=code, name=f"{code} College", state="Tamil Nadu",
                                          contact_name="Officer", email=email, phone="1")

    def make_fdr(self, institution, maturity, status=FDR.Status.ACTIVE):
        self.counter += 1
        return FDR.objects.create(
            institution=institution, fdr_number=f"R-{self.counter:04d}", bank="Sample National Bank",
            branch="Main", amount_paise=10000000, issue_date=maturity - timedelta(days=400),
            maturity_date=maturity, interest_rate="6.50", payout_type="cumulative",
            category="Security Deposit", status=status, submitted_by=self.admin,
        )


class ReminderEligibilityTests(ReminderTestBase):
    def test_sends_exactly_on_90_60_and_30_days(self):
        for days in (90, 60, 30):
            self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=days))
        summary = run_reminders(RUN_DATE)
        self.assertEqual(summary.counts["accepted"], 3)
        self.assertEqual(len(mail.outbox), 3)
        subjects = {m.subject for m in mail.outbox}
        self.assertEqual(subjects, {
            "FDR Maturity Reminder — R-0001 — 90 Days",
            "FDR Maturity Reminder — R-0002 — 60 Days",
            "FDR Maturity Reminder — R-0003 — 30 Days",
        })

    def test_no_reminder_on_other_days(self):
        for days in (91, 89, 61, 59, 31, 29, 0, -5):
            self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=days))
        run_reminders(RUN_DATE)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(ReminderDelivery.objects.count(), 0)

    def test_leap_year_month_boundary_is_counted_in_real_days(self):
        # 1 Feb 2028 to 1 May 2028 crosses 29 February (a leap day): exactly 90 days.
        maturity = date(2028, 5, 1)
        self.make_fdr(self.inst_a, maturity)
        summary = run_reminders(date(2028, 2, 1))
        self.assertEqual(summary.counts["accepted"], 1)
        self.assertIn("— 90 Days", mail.outbox[0].subject)

    def test_year_boundary(self):
        self.make_fdr(self.inst_a, date(2027, 1, 30))  # 30 days after 31 Dec 2026
        summary = run_reminders(date(2026, 12, 31))
        self.assertEqual(summary.counts["accepted"], 1)

    def test_ineligible_statuses_are_not_reminded(self):
        for status in (FDR.Status.MATURED, FDR.Status.RELEASE_REQUESTED, FDR.Status.RELEASED_CLOSED,
                       FDR.Status.RENEWED, FDR.Status.UNDER_VERIFICATION):
            self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=30), status=status)
        run_reminders(RUN_DATE)
        self.assertEqual(len(mail.outbox), 0)

    def test_nearing_maturity_status_is_reminded(self):
        self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=60), status=FDR.Status.NEARING_MATURITY)
        self.assertEqual(run_reminders(RUN_DATE).counts["accepted"], 1)


class ReminderDeliveryTests(ReminderTestBase):
    def test_repeated_runs_never_send_the_same_reminder_twice(self):
        self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=90))
        run_reminders(RUN_DATE)
        second = run_reminders(RUN_DATE)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(second.counts["already_sent"], 1)
        self.assertEqual(ReminderDelivery.objects.count(), 1)

    def test_recipient_is_the_institution_contact_and_each_institution_gets_its_own(self):
        self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=30))
        self.make_fdr(self.inst_b, RUN_DATE + timedelta(days=30))
        run_reminders(RUN_DATE)
        recipients = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(recipients, ["a-college@example.test", "b-college@example.test"])

    def test_failed_send_is_recorded_and_retried_later(self):
        fdr = self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=60))
        with mock.patch("reminders.services.EmailMultiAlternatives.send", side_effect=SMTPException("535 auth failed")):
            first = run_reminders(RUN_DATE)
        self.assertEqual(first.counts["failed"], 1)
        self.assertEqual(len(mail.outbox), 0)
        delivery = ReminderDelivery.objects.get(fdr=fdr)
        self.assertEqual(delivery.status, ReminderDelivery.Status.FAILED)
        self.assertIn("535", delivery.last_error)

        # Next day: the reminder is not due by date any more, but the failure is retried.
        second = run_reminders(RUN_DATE + timedelta(days=1))
        self.assertEqual(second.counts["accepted"], 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, ReminderDelivery.Status.ACCEPTED)
        self.assertEqual(delivery.attempts, 2)
        self.assertEqual(len(mail.outbox), 1)

    def test_missing_or_invalid_recipient_is_skipped_then_sent_after_fix(self):
        fdr = self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=30))
        self.inst_a.email = "not-an-email"
        self.inst_a.save()
        summary = run_reminders(RUN_DATE)
        self.assertEqual(summary.counts["skipped"], 1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(ReminderDelivery.objects.get(fdr=fdr).status, ReminderDelivery.Status.SKIPPED)

        self.inst_a.email = "fixed@example.test"
        self.inst_a.save()
        run_reminders(RUN_DATE + timedelta(days=1))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["fixed@example.test"])

    def test_gives_up_after_max_attempts(self):
        fdr = self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=30))
        with mock.patch("reminders.services.EmailMultiAlternatives.send", side_effect=SMTPException("down")):
            for offset in range(6):
                run_reminders(RUN_DATE + timedelta(days=offset))
        delivery = ReminderDelivery.objects.get(fdr=fdr)
        self.assertEqual(delivery.attempts, 5)

    def test_password_is_redacted_from_recorded_errors(self):
        from django.test import override_settings
        fdr = self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=30))
        with override_settings(EMAIL_HOST_PASSWORD="s3cret-pass"):
            with mock.patch("reminders.services.EmailMultiAlternatives.send",
                            side_effect=SMTPException("login with s3cret-pass rejected")):
                run_reminders(RUN_DATE)
        self.assertNotIn("s3cret-pass", ReminderDelivery.objects.get(fdr=fdr).last_error)


class DryRunAndCommandTests(ReminderTestBase):
    def test_dry_run_sends_nothing_and_records_nothing(self):
        self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=90))
        self.make_fdr(self.inst_b, RUN_DATE + timedelta(days=30))
        out = StringIO()
        call_command("send_fdr_reminders", "--date", "2026-10-27", "--dry-run", stdout=out)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(ReminderDelivery.objects.count(), 0)
        self.assertIn("DRY RUN", out.getvalue())
        self.assertIn("Would send:", out.getvalue())

    def test_command_reports_accepted_counts(self):
        self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=60))
        out = StringIO()
        call_command("send_fdr_reminders", "--date", "2026-10-27", stdout=out)
        self.assertIn("Accepted by mail server:           1", out.getvalue())

    def test_invalid_date_is_rejected(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("send_fdr_reminders", "--date", "27/10/2026")


class ReminderHistoryAccessTests(ReminderTestBase):
    def setUp(self):
        super().setUp()
        self.institution_user = User.objects.create_user(
            email="inst@t.test", password="Correct-horse-battery-9", name="Inst", role="institution_user",
            institution=self.inst_a)
        self.client = APIClient()

    def test_administrator_can_read_history(self):
        self.make_fdr(self.inst_a, RUN_DATE + timedelta(days=30))
        run_reminders(RUN_DATE)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/reminders/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 1)
        self.assertEqual(resp.json()["results"][0]["status"], "accepted")

    def test_institution_user_cannot_read_reminder_history(self):
        self.client.force_authenticate(user=self.institution_user)
        self.assertEqual(self.client.get("/api/reminders/").status_code, 403)
