from django.db import models

# Reminder intervals in calendar days before maturity (business rule, see README).
REMINDER_DAYS = (90, 60, 30)
# After this many failed sends, the reminder stops being retried and needs administrator attention.
MAX_ATTEMPTS = 5


class ReminderDelivery(models.Model):
    """Delivery history for one reminder event.

    One row per (FDR, reminder interval, maturity date). That combination is the
    idempotency key: the database refuses a second row for the same event, so a
    reminder is never recorded twice even if the job runs concurrently.

    "accepted" means the mail server accepted the message. It does NOT prove the
    institution received or read it.
    """

    class Status(models.TextChoices):
        ACCEPTED = "accepted", "Accepted by mail server"
        FAILED = "failed", "Failed (will be retried)"
        SKIPPED = "skipped", "Skipped (no valid recipient)"

    fdr = models.ForeignKey("fdrs.FDR", on_delete=models.PROTECT, related_name="reminder_deliveries")
    reminder_days = models.PositiveSmallIntegerField()
    maturity_date = models.DateField()
    recipient = models.EmailField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True, default="")
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["fdr", "reminder_days", "maturity_date"], name="unique_reminder_per_event",
            ),
        ]
        indexes = [models.Index(fields=["status", "maturity_date"])]

    def __str__(self):
        return f"{self.fdr.fdr_number} · {self.reminder_days}-day reminder · {self.status}"
