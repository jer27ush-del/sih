import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    """In-portal inbox item. Each one links straight to the relevant FDR or request."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=32)
    message = models.CharField(max_length=500)
    link = models.CharField(max_length=255, blank=True, default="")
    read_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]


class ReminderLog(models.Model):
    """Idempotency record: a reminder with a given key is sent at most once, so re-running
    the daily job never produces duplicate alerts."""

    key = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=32)
    fdr = models.ForeignKey("fdrs.FDR", null=True, blank=True, on_delete=models.PROTECT, related_name="reminders")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
