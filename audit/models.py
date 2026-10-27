from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone


class AppendOnlyQuerySet(models.QuerySet):
    """Bulk update/delete would bypass the model guard, so they are blocked here too."""

    def update(self, **kwargs):
        raise RuntimeError("Audit entries are append-only and cannot be updated.")

    def delete(self):
        raise RuntimeError("Audit entries are append-only and cannot be deleted.")


class AuditLog(models.Model):
    """Append-only record of every submission, change and decision.

    The application database role should also be granted only INSERT and SELECT
    on this table (see README, "Hardening the audit table").
    """

    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_entries"
    )
    actor_label = models.CharField(max_length=255)  # snapshot, e.g. "Sample Auditor (auditor)" or "System"
    action = models.CharField(max_length=100, db_index=True)
    entity = models.CharField(max_length=50, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    old_value = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    new_value = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Audit entries are append-only and cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit entries are append-only and cannot be deleted.")

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.action} {self.entity}:{self.entity_id}"
