from django.conf import settings
from django.db import models


def default_thresholds():
    return [90, 60, 30]


def default_banks():
    return ["Sample National Bank", "Demo State Bank", "Example Cooperative Bank"]


def default_categories():
    return ["Security Deposit", "Performance Guarantee", "Other"]


def default_document_types():
    return ["application/pdf", "image/png", "image/jpeg"]


class SystemSettings(models.Model):
    """Single-row configuration, editable only by administrators. Every change is audited."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    maturity_thresholds = models.JSONField(default=default_thresholds)
    escalation_contacts = models.JSONField(default=list, blank=True)
    overdue_escalation_days = models.PositiveIntegerField(default=7)
    query_followup_days = models.PositiveIntegerField(default=7)
    document_max_bytes = models.PositiveBigIntegerField(default=10 * 1024 * 1024)
    allowed_document_types = models.JSONField(default=default_document_types)
    banks = models.JSONField(default=default_banks)
    categories = models.JSONField(default=default_categories)
    minimum_tenure_days = models.PositiveIntegerField(default=365)
    amount_min_paise = models.PositiveBigIntegerField(default=100)
    amount_max_paise = models.PositiveBigIntegerField(default=100_000_000_000)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "system settings"
        verbose_name_plural = "system settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
