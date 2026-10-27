import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower


class FDR(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "Submitted", "Submitted"
        UNDER_VERIFICATION = "Under Verification", "Under Verification"
        QUERY_RAISED = "Query Raised", "Query Raised"
        CORRECTED = "Corrected", "Corrected"
        VERIFIED = "Verified", "Verified"
        ACTIVE = "Active", "Active"
        NEARING_MATURITY = "Nearing Maturity", "Nearing Maturity"
        MATURED = "Matured", "Matured"
        RENEWED = "Renewed", "Renewed"
        RELEASE_REQUESTED = "Release Requested", "Release Requested"
        RELEASED_CLOSED = "Released / Closed", "Released / Closed"
        REJECTED = "Rejected", "Rejected"

    class PayoutType(models.TextChoices):
        CUMULATIVE = "cumulative", "Cumulative"
        PERIODIC = "periodic", "Periodic"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey("institutions.Institution", on_delete=models.PROTECT, related_name="fdrs")
    fdr_number = models.CharField(max_length=64)
    bank = models.CharField(max_length=120)
    branch = models.CharField(max_length=120)
    # Money is stored as integer paise, never as floating point.
    amount_paise = models.BigIntegerField()
    issue_date = models.DateField()
    maturity_date = models.DateField()
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    payout_type = models.CharField(max_length=12, choices=PayoutType.choices)
    category = models.CharField(max_length=120)
    lien_marked = models.BooleanField(default=False)
    held_in_favour_of_aicte = models.BooleanField(default=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    status_note = models.TextField(blank=True, default="")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children",
    )
    review_flag = models.BooleanField(default=False)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="submitted_fdrs")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["institution", "status"]),
            models.Index(fields=["maturity_date"]),
        ]
        constraints = [
            # The same FDR number cannot be entered twice for the same bank (case-insensitive).
            models.UniqueConstraint(Lower("fdr_number"), Lower("bank"), name="fdr_unique_number_per_bank"),
            models.CheckConstraint(condition=Q(amount_paise__gt=0), name="fdr_amount_positive"),
            models.CheckConstraint(condition=Q(maturity_date__gt=F("issue_date")), name="fdr_maturity_after_issue"),
        ]

    def __str__(self):
        return f"{self.fdr_number} ({self.bank})"


class Document(models.Model):
    class ScanStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        CLEAN = "clean", "Clean"
        INFECTED = "infected", "Infected"
        UNSCANNED = "unscanned", "Unscanned (no scanner configured)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fdr = models.ForeignKey(FDR, on_delete=models.PROTECT, related_name="documents")
    storage_name = models.CharField(max_length=255, unique=True)  # random path, never shown to users
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=64)
    size_bytes = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    version = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)
    scan_status = models.CharField(max_length=16, choices=ScanStatus.choices, default=ScanStatus.PENDING)

    class Meta:
        ordering = ["fdr", "-version"]
        constraints = [models.UniqueConstraint(fields=["fdr", "version"], name="document_unique_version")]


class VerificationRun(models.Model):
    """One run of the automated checks. Kept as history, so every screening is traceable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fdr = models.ForeignKey(FDR, on_delete=models.PROTECT, related_name="verification_runs")
    rule_results = models.JSONField(default=dict)
    run_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )  # null = system run
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class BankConfirmation(models.Model):
    class Mode(models.TextChoices):
        LETTER = "letter", "Confirmation letter"
        EMAIL = "email", "Email from bank"
        PHONE = "phone", "Phone call"
        PORTAL = "bank_portal", "Bank portal"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fdr = models.ForeignKey(FDR, on_delete=models.PROTECT, related_name="bank_confirmations")
    confirmed_on = models.DateField()
    mode = models.CharField(max_length=16, choices=Mode.choices)
    reference = models.CharField(max_length=120)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Query(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fdr = models.ForeignKey(FDR, on_delete=models.PROTECT, related_name="queries")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    message = models.TextField()
    reply = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    raised_at = models.DateTimeField(auto_now_add=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-raised_at"]


class FdrRequest(models.Model):
    """A renewal (replacement FDR) or a release / premature withdrawal request."""

    class RequestType(models.TextChoices):
        RENEWAL = "renewal", "Renewal"
        RELEASE = "release", "Release"

    class ReleaseKind(models.TextChoices):
        AT_MATURITY = "at_maturity", "Release at maturity"
        PREMATURE = "premature", "Premature withdrawal"

    class Status(models.TextChoices):
        SUBMITTED = "Submitted", "Submitted"
        RECOMMENDED = "Recommended", "Recommended"
        APPROVED = "Approved", "Approved"
        REJECTED = "Rejected", "Rejected"
        COMPLETED = "Completed", "Completed"

    OPEN_STATUSES = (Status.SUBMITTED, Status.RECOMMENDED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fdr = models.ForeignKey(FDR, on_delete=models.PROTECT, related_name="requests")
    request_type = models.CharField(max_length=12, choices=RequestType.choices)
    release_kind = models.CharField(max_length=12, choices=ReleaseKind.choices, blank=True, default="")
    reason = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED)
    previous_status = models.CharField(max_length=32, blank=True, default="")  # restored if rejected
    bank_terms_noted = models.BooleanField(default=False)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    recommended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    recommended_at = models.DateTimeField(null=True, blank=True)
    recommendation_note = models.TextField(blank=True, default="")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    action_taken = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Database-level guarantee: at most one open request per FDR.
            models.UniqueConstraint(
                fields=["fdr"],
                condition=Q(status__in=["Submitted", "Recommended"]),
                name="one_open_request_per_fdr",
            ),
        ]
