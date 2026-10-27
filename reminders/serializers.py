from rest_framework import serializers

from .models import ReminderDelivery


class ReminderDeliverySerializer(serializers.ModelSerializer):
    fdr_number = serializers.CharField(source="fdr.fdr_number", read_only=True)
    institution_code = serializers.CharField(source="fdr.institution.code", read_only=True)

    class Meta:
        model = ReminderDelivery
        fields = ["id", "fdr_number", "institution_code", "reminder_days", "maturity_date", "recipient",
                  "status", "attempts", "last_error", "accepted_at", "created_at"]
        read_only_fields = fields
