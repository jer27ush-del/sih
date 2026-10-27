from django.test import TestCase

from accounts.models import User
from audit.models import AuditLog
from audit.services import record_audit


class AuditAppendOnlyTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(email="a@t.test", password="x-x-x-x-x-x-x-9", name="A", role="auditor")
        self.entry = record_audit(action="test.action", entity="FDR", entity_id="123", actor=self.actor,
                                  old={"status": "Submitted"}, new={"status": "Under Verification"})

    def test_existing_entry_cannot_be_edited(self):
        self.entry.action = "tampered"
        with self.assertRaises(RuntimeError):
            self.entry.save()

    def test_entry_cannot_be_deleted(self):
        with self.assertRaises(RuntimeError):
            self.entry.delete()

    def test_bulk_update_and_delete_are_blocked_too(self):
        with self.assertRaises(RuntimeError):
            AuditLog.objects.filter(pk=self.entry.pk).update(action="tampered")
        with self.assertRaises(RuntimeError):
            AuditLog.objects.filter(pk=self.entry.pk).delete()

    def test_auditor_can_read_but_nothing_can_write_through_the_api(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.actor)
        resp = client.get("/api/audit-logs/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.json()["count"], 1)
        self.assertIn(client.delete(f"/api/audit-logs/{self.entry.pk}/").status_code, (404, 405))  # no delete route exists
