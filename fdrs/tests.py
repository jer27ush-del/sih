import csv
import io
import shutil
import tempfile
from datetime import timedelta
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from common.exceptions import BusinessRuleError
from fdrs.importer import ImportFormatError, classify, parse_amount_paise, parse_csv
from fdrs.jobs import run_daily_jobs
from fdrs.maturity import reminder_window
from fdrs.models import FDR, FdrRequest
from fdrs.rules import run_rules
from fdrs.workflow import can_transition, change_status
from institutions.models import Institution
from notifications.models import Notification, ReminderLog

PASSWORD = "Correct-horse-battery-9"
TMP_UPLOADS = tempfile.mkdtemp(prefix="fdr-test-uploads-")
S = FDR.Status


def pdf_file(name="fdr.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n% sample test document\n", content_type="application/pdf")


def fdr_payload(**overrides):
    data = {
        "fdr_number": "TEST-FDR-1", "bank": "Sample National Bank", "branch": "Chennai Main",
        "amount_paise": 50000000, "issue_date": "2026-01-15", "maturity_date": "2027-01-15",
        "interest_rate": "6.50", "payout_type": "cumulative", "category": "Security Deposit",
    }
    data.update(overrides)
    return data


@override_settings(PRIVATE_UPLOAD_ROOT=TMP_UPLOADS)
class Base(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_UPLOADS, ignore_errors=True)

    def setUp(self):
        self.inst = Institution.objects.create(code="T001", name="Test College", state="Tamil Nadu",
                                               contact_name="A", email="a@t.test", phone="1")
        self.other = Institution.objects.create(code="T002", name="Other College", state="Karnataka",
                                                contact_name="B", email="b@t.test", phone="2")
        self.inst_user = self.make_user("inst@t.test", "Inst User", "institution_user", self.inst)
        self.other_user = self.make_user("other@t.test", "Other User", "institution_user", self.other)
        self.officer = self.make_user("officer@t.test", "Officer", "scrutiny_officer")
        self.admin = self.make_user("admin@t.test", "Admin", "administrator")
        self.admin2 = self.make_user("admin2@t.test", "Admin Two", "administrator")
        self.auditor = self.make_user("aud@t.test", "Auditor", "auditor")
        self.client = APIClient()

    def make_user(self, email, name, role, institution=None):
        return User.objects.create_user(email=email, password=PASSWORD, name=name, role=role,
                                        institution=institution)

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def register(self, user=None, **overrides):
        self.as_user(user or self.inst_user)
        return self.client.post("/api/fdrs/", fdr_payload(**overrides), format="json")

    def make_verified_fdr(self, **overrides):
        """Helper: create an FDR through the real workflow and carry it to Active."""
        resp = self.register(**overrides)
        self.assertEqual(resp.status_code, 201, resp.json())
        fdr_id = resp.json()["id"]
        self.as_user(self.inst_user)
        self.client.post(f"/api/fdrs/{fdr_id}/documents/", {"file": pdf_file()}, format="multipart")
        self.as_user(self.officer)
        self.client.post(f"/api/fdrs/{fdr_id}/bank-confirmation/",
                         {"confirmed_on": "2026-01-20", "mode": "letter", "reference": "BANK-REF-1"}, format="json")
        resp = self.client.post(f"/api/fdrs/{fdr_id}/decision/", {"decision": "Verified", "reason": "Checked"},
                                format="json")
        self.assertEqual(resp.status_code, 200, resp.json())
        self.assertEqual(resp.json()["status"], "Active")
        return FDR.objects.get(pk=fdr_id)


class RegistrationTests(Base):
    def test_institution_user_registers_fdr_which_enters_verification(self):
        resp = self.register()
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["status"], "Under Verification")
        self.assertTrue(body["reviewFlag"], "no document yet, so the record must be flagged")
        self.assertEqual(body["institutionCode"], "T001")
        self.assertTrue(AuditLog.objects.filter(action="fdr.submitted", entity_id=body["id"]).exists())

    def test_same_fdr_number_for_same_bank_is_rejected(self):
        self.register()
        resp = self.register(fdr_number="test-fdr-1")  # case-insensitive duplicate
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"]["code"], "conflict")

    def test_institution_user_cannot_register_for_another_institution(self):
        resp = self.register(institution=str(self.other.pk))
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["institutionCode"], "T001")

    def test_bank_outside_configured_list_is_rejected(self):
        resp = self.register(bank="Unknown Bank Ltd")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("bank", resp.json()["error"]["fields"])

    def test_maturity_must_follow_issue_date(self):
        resp = self.register(issue_date="2027-02-01", maturity_date="2027-01-15")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("maturityDate", resp.json()["error"]["fields"])

    def test_auditor_cannot_register(self):
        self.as_user(self.auditor)
        resp = self.client.post("/api/fdrs/", fdr_payload(), format="json")
        self.assertEqual(resp.status_code, 403)


class VisibilityTests(Base):
    def test_institution_user_cannot_see_another_institutions_fdr(self):
        fdr_id = self.register().json()["id"]
        self.as_user(self.other_user)
        self.assertEqual(self.client.get(f"/api/fdrs/{fdr_id}/").status_code, 404)  # 404, not 403: no existence leak
        self.assertEqual(self.client.get("/api/fdrs/").json()["count"], 0)

    def test_admin_and_auditor_see_all_records(self):
        self.register()
        self.as_user(self.admin)
        self.assertEqual(self.client.get("/api/fdrs/").json()["count"], 1)
        self.as_user(self.auditor)
        self.assertEqual(self.client.get("/api/fdrs/").json()["count"], 1)


class DocumentTests(Base):
    def setUp(self):
        super().setUp()
        self.fdr_id = self.register().json()["id"]
        self.as_user(self.inst_user)

    def test_real_pdf_is_stored_with_checksum_and_version(self):
        resp = self.client.post(f"/api/fdrs/{self.fdr_id}/documents/", {"file": pdf_file()}, format="multipart")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["version"], 1)
        self.assertEqual(len(resp.json()["sha256"]), 64)

    def test_reupload_keeps_old_version_and_marks_it_inactive(self):
        self.client.post(f"/api/fdrs/{self.fdr_id}/documents/", {"file": pdf_file()}, format="multipart")
        resp = self.client.post(f"/api/fdrs/{self.fdr_id}/documents/", {"file": pdf_file("v2.pdf")}, format="multipart")
        self.assertEqual(resp.json()["version"], 2)
        self.assertEqual(FDR.objects.get(pk=self.fdr_id).documents.filter(active=True).count(), 1)
        self.assertEqual(FDR.objects.get(pk=self.fdr_id).documents.count(), 2)

    def test_file_with_pdf_extension_but_wrong_content_is_rejected(self):
        fake = SimpleUploadedFile("report.pdf", b"<script>alert(1)</script>", content_type="application/pdf")
        resp = self.client.post(f"/api/fdrs/{self.fdr_id}/documents/", {"file": fake}, format="multipart")
        self.assertEqual(resp.status_code, 400)

    def test_empty_file_is_rejected(self):
        empty = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")
        resp = self.client.post(f"/api/fdrs/{self.fdr_id}/documents/", {"file": empty}, format="multipart")
        self.assertEqual(resp.status_code, 400)

    def test_download_is_allowed_for_owner_audited_and_hidden_from_others(self):
        doc_id = self.client.post(f"/api/fdrs/{self.fdr_id}/documents/", {"file": pdf_file()},
                                  format="multipart").json()["id"]
        resp = self.client.get(f"/api/documents/{doc_id}/download/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp["Content-Disposition"])
        self.assertTrue(AuditLog.objects.filter(action="document.downloaded", entity_id=doc_id).exists())
        self.as_user(self.other_user)
        self.assertEqual(self.client.get(f"/api/documents/{doc_id}/download/").status_code, 404)


class WorkflowTests(Base):
    def test_full_review_loop_from_submission_to_active(self):
        fdr_id = self.register().json()["id"]
        self.as_user(self.inst_user)
        self.client.post(f"/api/fdrs/{fdr_id}/documents/", {"file": pdf_file()}, format="multipart")

        self.as_user(self.officer)
        query = self.client.post(f"/api/fdrs/{fdr_id}/queries/", {"message": "Attach a clearer copy"}, format="json")
        self.assertEqual(query.status_code, 201)
        self.assertEqual(FDR.objects.get(pk=fdr_id).status, S.QUERY_RAISED)

        self.as_user(self.inst_user)
        reply = self.client.post(f"/api/queries/{query.json()['id']}/reply/", {"reply": "Uploaded"}, format="json")
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(FDR.objects.get(pk=fdr_id).status, S.CORRECTED)

        self.as_user(self.officer)
        verify = self.client.post(f"/api/fdrs/{fdr_id}/verify/")
        self.assertEqual(verify.status_code, 200)
        self.assertEqual(FDR.objects.get(pk=fdr_id).status, S.UNDER_VERIFICATION)

        blocked = self.client.post(f"/api/fdrs/{fdr_id}/decision/", {"decision": "Verified", "reason": "ok"},
                                   format="json")
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("bank confirmation", blocked.json()["error"]["message"].lower())

        self.client.post(f"/api/fdrs/{fdr_id}/bank-confirmation/",
                         {"confirmed_on": "2026-01-20", "mode": "email", "reference": "REF-9"}, format="json")
        done = self.client.post(f"/api/fdrs/{fdr_id}/decision/", {"decision": "Verified", "reason": "Confirmed"},
                                format="json")
        self.assertEqual(done.json()["status"], "Active")
        self.assertTrue(AuditLog.objects.filter(action="fdr.status_changed", entity_id=fdr_id).count() >= 5)

    def test_institution_user_cannot_verify_or_raise_queries(self):
        fdr_id = self.register().json()["id"]
        self.assertEqual(self.client.post(f"/api/fdrs/{fdr_id}/decision/",
                                          {"decision": "Verified", "reason": "x"}, format="json").status_code, 403)
        self.assertEqual(self.client.post(f"/api/fdrs/{fdr_id}/queries/", {"message": "x"},
                                          format="json").status_code, 403)

    def test_rejection_requires_a_reason(self):
        fdr_id = self.register().json()["id"]
        self.as_user(self.officer)
        resp = self.client.post(f"/api/fdrs/{fdr_id}/decision/", {"decision": "Rejected", "reason": ""}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_admin_cannot_reply_to_queries_on_behalf_of_institution(self):
        fdr_id = self.register().json()["id"]
        self.as_user(self.officer)
        query_id = self.client.post(f"/api/fdrs/{fdr_id}/queries/", {"message": "Check"}, format="json").json()["id"]
        self.as_user(self.admin)
        self.assertEqual(self.client.post(f"/api/queries/{query_id}/reply/", {"reply": "x"},
                                          format="json").status_code, 403)

    def test_status_machine_blocks_unlisted_transitions(self):
        self.assertFalse(can_transition(S.SUBMITTED, S.VERIFIED, "scrutiny_officer"))
        self.assertFalse(can_transition(S.RELEASE_REQUESTED, S.RELEASED_CLOSED, "scrutiny_officer"))
        self.assertTrue(can_transition(S.UNDER_VERIFICATION, S.VERIFIED, "scrutiny_officer"))
        fdr = FDR.objects.get(pk=self.register().json()["id"])
        with self.assertRaises(BusinessRuleError):
            change_status(fdr, S.MATURED, self.officer)  # Under Verification -> Matured is not a valid move


class ReleaseTests(Base):
    def test_premature_release_requires_bank_terms_acknowledged(self):
        fdr = self.make_verified_fdr()
        self.as_user(self.inst_user)
        resp = self.client.post(f"/api/fdrs/{fdr.pk}/requests/",
                                {"release_kind": "premature", "reason": "Cash needed", "bank_terms_noted": False},
                                format="json")
        self.assertEqual(resp.status_code, 400)

    def test_release_request_separation_of_duties_and_final_release(self):
        fdr = self.make_verified_fdr()
        self.as_user(self.inst_user)
        self.client.post(f"/api/fdrs/{fdr.pk}/documents/", {"file": pdf_file("support.pdf")}, format="multipart")
        req = self.client.post(f"/api/fdrs/{fdr.pk}/requests/",
                               {"release_kind": "premature", "reason": "Project closed", "bank_terms_noted": True},
                               format="json")
        self.assertEqual(req.status_code, 201)
        req_id = req.json()["id"]
        fdr.refresh_from_db()
        self.assertEqual(fdr.status, S.RELEASE_REQUESTED)

        self.as_user(self.officer)
        self.assertEqual(self.client.post(f"/api/requests/{req_id}/recommend/", {"note": "Looks fine"},
                                          format="json").status_code, 200)

        self.as_user(self.admin)
        self.assertEqual(self.client.post(f"/api/requests/{req_id}/decision/",
                                          {"decision": "approve", "action_taken": "Released"},
                                          format="json").status_code, 200)
        fdr.refresh_from_db()
        self.assertEqual(fdr.status, S.RELEASED_CLOSED)

    def test_admin_who_recommended_cannot_also_approve(self):
        fdr = self.make_verified_fdr()
        self.as_user(self.inst_user)
        req_id = self.client.post(f"/api/fdrs/{fdr.pk}/requests/",
                                  {"release_kind": "premature", "reason": "Need funds", "bank_terms_noted": True},
                                  format="json").json()["id"]
        self.as_user(self.admin)
        self.client.post(f"/api/requests/{req_id}/recommend/", {}, format="json")
        resp = self.client.post(f"/api/requests/{req_id}/decision/",
                                {"decision": "approve", "action_taken": "Released"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Separation of duties", resp.json()["error"]["message"])

        self.as_user(self.admin2)
        self.assertEqual(self.client.post(f"/api/requests/{req_id}/decision/",
                                          {"decision": "approve", "action_taken": "Released"},
                                          format="json").status_code, 200)

    def test_rejected_release_restores_previous_status(self):
        fdr = self.make_verified_fdr()
        self.as_user(self.inst_user)
        req_id = self.client.post(f"/api/fdrs/{fdr.pk}/requests/",
                                  {"release_kind": "premature", "reason": "Need funds", "bank_terms_noted": True},
                                  format="json").json()["id"]
        self.as_user(self.officer)
        self.client.post(f"/api/requests/{req_id}/recommend/", {}, format="json")
        self.as_user(self.admin)
        self.client.post(f"/api/requests/{req_id}/decision/", {"decision": "reject", "reason": "Penalty too high"},
                         format="json")
        fdr.refresh_from_db()
        self.assertEqual(fdr.status, S.ACTIVE)

    def test_renewal_replaces_old_fdr_and_closes_it_once_new_one_is_verified(self):
        old = self.make_verified_fdr()
        old.maturity_date = timezone.localdate() + timedelta(days=20)
        old.status = S.NEARING_MATURITY
        old.save()
        self.as_user(self.inst_user)
        resp = self.client.post(f"/api/fdrs/{old.pk}/renewals/", fdr_payload(fdr_number="RENEW-1",
                                issue_date="2026-11-01", maturity_date="2027-11-01"), format="json")
        self.assertEqual(resp.status_code, 201)
        new_id = resp.json()["id"]
        old.refresh_from_db()
        self.assertEqual(old.status, S.RENEWED)

        self.client.post(f"/api/fdrs/{new_id}/documents/", {"file": pdf_file()}, format="multipart")
        self.as_user(self.officer)
        bc = self.client.post(f"/api/fdrs/{new_id}/bank-confirmation/",
                              {"confirmed_on": "2026-10-20", "mode": "phone", "reference": "R-2"}, format="json")
        dec = self.client.post(f"/api/fdrs/{new_id}/decision/", {"decision": "Verified", "reason": "ok"}, format="json")
        self.assertEqual(bc.status_code, 201, bc.json())
        self.assertEqual(dec.status_code, 200, dec.json())
        old.refresh_from_db()
        self.assertEqual(old.status, S.RELEASED_CLOSED)
        self.assertEqual(FdrRequest.objects.get(fdr=old, request_type="renewal").status, "Completed")


class MaturityJobTests(Base):
    def make_active(self, maturity_offset_days, today):
        return FDR.objects.create(
            institution=self.inst, fdr_number=f"JOB-{maturity_offset_days}", bank="Sample National Bank",
            branch="Chennai", amount_paise=100000, issue_date=today - timedelta(days=400),
            maturity_date=today + timedelta(days=maturity_offset_days), interest_rate="6.00",
            payout_type="cumulative", category="Security Deposit", status=S.ACTIVE, submitted_by=self.admin,
        )

    def test_active_fdr_enters_nearing_window_and_reminder_is_sent_once(self):
        today = timezone.localdate()
        fdr = self.make_active(25, today)
        run_daily_jobs(today)
        fdr.refresh_from_db()
        self.assertEqual(fdr.status, S.NEARING_MATURITY)
        self.assertTrue(ReminderLog.objects.filter(key=f"maturity:{fdr.pk}:30").exists())

        before = Notification.objects.count()
        run_daily_jobs(today)  # re-running must not duplicate alerts
        self.assertEqual(Notification.objects.count(), before)
        self.assertEqual(ReminderLog.objects.filter(fdr=fdr).count(), 1)

    def test_maturity_date_passed_moves_to_matured_in_one_run(self):
        today = timezone.localdate()
        fdr = self.make_active(-1, today)
        run_daily_jobs(today)
        fdr.refresh_from_db()
        self.assertEqual(fdr.status, S.MATURED)

    def test_long_unactioned_maturity_triggers_overdue_escalation(self):
        today = timezone.localdate()
        fdr = self.make_active(-30, today)
        fdr.status = S.MATURED
        fdr.save()
        run_daily_jobs(today)
        self.assertTrue(ReminderLog.objects.filter(key=f"overdue:{fdr.pk}", kind="overdue").exists())

    def test_reminder_window_helper_picks_tightest_crossed_threshold(self):
        self.assertEqual(reminder_window(25, [90, 60, 30]), 30)
        self.assertEqual(reminder_window(100, [90, 60, 30]), None)


class ImportTests(Base):
    def csv_upload(self, rows, header=None):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header or ["fdr_number", "bank", "branch", "amount_rupees", "issue_date", "maturity_date",
                                   "interest_rate", "payout_type", "category"])
        writer.writerows(rows)
        return SimpleUploadedFile("import.csv", buffer.getvalue().encode("utf-8"), content_type="text/csv")

    def test_preview_classifies_rows_then_commit_imports_only_valid_ones_as_one_batch(self):
        self.make_verified_fdr(fdr_number="ALREADY-1")
        rows = [
            ["NEW-1", "Sample National Bank", "Chennai, Main", "500000.50", "2026-01-15", "2027-01-15", "6.5",
             "cumulative", "Security Deposit"],
            ["BAD-1", "Sample National Bank", "Chennai", "abc", "2026-01-15", "2027-01-15", "6.5",
             "cumulative", "Security Deposit"],
            ["ALREADY-1", "Sample National Bank", "Chennai", "1000", "2026-01-15", "2027-01-15", "6.5",
             "cumulative", "Security Deposit"],
        ]
        self.as_user(self.inst_user)
        preview = self.client.post("/api/fdrs/import/", {"file": self.csv_upload(rows)}, format="multipart")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["summary"], {"valid": 1, "error": 1, "duplicate": 1})

        count_before = FDR.objects.count()
        batch = self.client.post("/api/fdrs/import/", {"file": self.csv_upload(rows), "commit": "true"},
                                 format="multipart")
        self.assertEqual(batch.status_code, 201)
        self.assertEqual(batch.json()["created"], 1)
        self.assertEqual(FDR.objects.count(), count_before + 1)
        self.assertEqual(AuditLog.objects.filter(action="fdr.bulk_import").count(), 1)
        self.assertEqual(FDR.objects.get(fdr_number="NEW-1").amount_paise, 50000050)

    def test_missing_required_column_is_rejected(self):
        upload = self.csv_upload([], header=["fdr_number", "bank"])
        self.as_user(self.inst_user)
        resp = self.client.post("/api/fdrs/import/", {"file": upload}, format="multipart")
        self.assertEqual(resp.status_code, 400)

    def test_money_is_parsed_into_exact_paise(self):
        self.assertEqual(parse_amount_paise("5,00,000.50"), 50000050)
        self.assertEqual(parse_amount_paise("500000"), 50000000)
        for bad in ["1.005", "-5", "0", "NaN", "abc"]:
            with self.assertRaises(ValueError, msg=bad):
                parse_amount_paise(bad)

    def test_quoted_commas_are_parsed_correctly(self):
        data = b'fdr_number,bank,branch,amount_rupees,issue_date,maturity_date,interest_rate,payout_type,category\n' \
               b'Q-1,"Sample National Bank","Chennai, Main Road",1000,2026-01-01,2027-01-01,6,periodic,Other\n'
        rows = parse_csv(data, max_bytes=10_000)
        self.assertEqual(rows[0]["data"]["branch"], "Chennai, Main Road")

    def test_non_utf8_file_is_rejected(self):
        with self.assertRaises(ImportFormatError):
            parse_csv("fdr_number\n\xff\xfe".encode("latin-1"), max_bytes=10_000)

    def test_classify_flags_repeats_within_one_file(self):
        row = lambda line: {"line": line, "data": {"fdr_number": "DUP", "bank": "Sample National Bank",
                                                  "category": "Other"}, "errors": [], "raw": {}}
        result = classify([row(2), row(3)], existing_keys=set(), banks=["Sample National Bank"],
                          categories=["Other"])
        self.assertEqual([r["status"] for r in result], ["valid", "duplicate"])


class RulesTests(TestCase):
    def rules(self, **overrides):
        base = dict(
            fdr_number="A-1", bank="Sample National Bank", branch="Chennai", amount_paise=50000000,
            issue_date=timezone.localdate() - timedelta(days=30), maturity_date=timezone.localdate() + timedelta(days=400),
            documents=[{"mime_type": "application/pdf", "size_bytes": 500, "active": True, "scan_status": "clean"}],
            duplicate_exists=False, bank_confirmed=False, allowed_mime_types=["application/pdf"],
            minimum_tenure_days=365, amount_min_paise=100, amount_max_paise=10**11,
        )
        base.update(overrides)
        return run_rules(**base)

    def test_clean_record_passes_all_but_bank_confirmation(self):
        results = self.rules(bank_confirmed=True)
        self.assertTrue(all(flag == "pass" for flag in results.values()), results)

    def test_missing_bank_confirmation_fails_and_blocks_verification(self):
        self.assertEqual(self.rules()["bank_confirmation"], "fail")

    def test_duplicate_reference_fails(self):
        self.assertEqual(self.rules(duplicate_exists=True)["duplicate_reference"], "fail")

    def test_short_tenure_and_missing_document_are_warnings(self):
        results = self.rules(maturity_date=timezone.localdate() + timedelta(days=60), documents=[])
        self.assertEqual(results["tenure_validity"], "warning")
        self.assertEqual(results["document_quality"], "warning")
        self.assertEqual(results["required_fields"], "fail")
