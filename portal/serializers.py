from rest_framework import serializers

from .models import SystemSettings

SETTING_FIELDS = [
    "maturity_thresholds", "escalation_contacts", "overdue_escalation_days", "query_followup_days",
    "document_max_bytes", "allowed_document_types", "banks", "categories", "minimum_tenure_days",
    "amount_min_paise", "amount_max_paise",
]
ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg"}


class SystemSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSettings
        fields = SETTING_FIELDS

    def validate_maturity_thresholds(self, value):
        if not value or any(not isinstance(v, int) or v < 1 or v > 3650 for v in value):
            raise serializers.ValidationError("Enter one or more whole numbers of days between 1 and 3650.")
        return sorted(set(value), reverse=True)

    def validate_banks(self, value):
        cleaned = [b.strip() for b in value if isinstance(b, str) and b.strip()]
        if not cleaned:
            raise serializers.ValidationError("Keep at least one bank in the list.")
        return cleaned

    def validate_categories(self, value):
        cleaned = [c.strip() for c in value if isinstance(c, str) and c.strip()]
        if not cleaned:
            raise serializers.ValidationError("Keep at least one deposit category.")
        return cleaned

    def validate_allowed_document_types(self, value):
        if not set(value) or not set(value) <= ALLOWED_TYPES:
            raise serializers.ValidationError("Allowed types can only be application/pdf, image/png and image/jpeg.")
        return value

    def validate(self, attrs):
        low = attrs.get("amount_min_paise", getattr(self.instance, "amount_min_paise", 0))
        high = attrs.get("amount_max_paise", getattr(self.instance, "amount_max_paise", 0))
        if low > high:
            raise serializers.ValidationError({"amount_max_paise": "The maximum must be at least the minimum."})
        return attrs
