from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from institutions.models import Institution

PASSWORD = "Correct-horse-battery-9"


class LoginAndAccountTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="officer@t.test", password=PASSWORD, name="Officer",
                                             role="scrutiny_officer")
        self.client = APIClient()

    def login(self, password=PASSWORD, email="officer@t.test"):
        return self.client.post("/api/auth/login/", {"email": email, "password": password}, format="json")

    def test_successful_login_returns_profile_with_camel_case_fields(self):
        resp = self.login()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["role"], "scrutiny_officer")
        self.assertEqual(resp.json()["status"], "Active")

    def test_wrong_password_gets_generic_message(self):
        resp = self.login(password="wrong-password-here")
        self.assertIn(resp.status_code, (401, 403))
        self.assertEqual(resp.json()["error"]["message"], "Invalid email or password.")

    def test_account_locks_after_repeated_failures_even_with_correct_password(self):
        for _ in range(5):
            self.login(password="wrong-password-here")
        resp = self.login()  # correct password, but the account is now locked
        self.assertEqual(resp.status_code, 423)
        self.assertEqual(resp.json()["error"]["code"], "account_locked")

    def test_deactivated_user_cannot_sign_in(self):
        self.user.is_active = False
        self.user.save()
        self.assertIn(self.login().status_code, (401, 403))

    def test_password_reset_request_gives_same_answer_for_unknown_email(self):
        known = self.client.post("/api/auth/password/reset/", {"email": "officer@t.test"}, format="json")
        unknown = self.client.post("/api/auth/password/reset/", {"email": "nobody@t.test"}, format="json")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json(), unknown.json())

    def test_institution_user_must_belong_to_an_institution(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(email="x@t.test", password=PASSWORD, name="X", role="institution_user")

    def test_only_administrators_can_manage_institutions(self):
        Institution.objects.create(code="T9", name="N", state="S", contact_name="c", email="a@t.test", phone="1")
        self.client.force_authenticate(user=self.user)
        resp = self.client.post("/api/institutions/", {"code": "T10", "name": "New", "state": "S",
                                                       "contact_name": "c", "email": "b@t.test", "phone": "1"},
                                format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.client.get("/api/institutions/").status_code, 200)  # officers can view
