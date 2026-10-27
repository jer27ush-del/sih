from django.utils import timezone
from rest_framework import serializers

from institutions.models import Institution
from portal.models import SystemSettings

from .maturity import days_to_maturity
from notifications.models import ReminderLog

from .models import FDR, BankConfirmation, Document, FdrRequest, Query, VerificationRun


def _name(user):
    return user.name if user else "System"


class DocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "original_name", "mime_type", "size_bytes", "sha256", "version",
                  "uploaded_by_name", "uploaded_at", "active", "scan_status"]
        read_only_fields = fields

    def get_uploaded_by_name(self, obj):
        return _name(obj.uploaded_by)


class VerificationRunSerializer(serializers.ModelSerializer):
    run_by_name = serializers.SerializerMethodField()

    class Meta:
        model = VerificationRun
        fields = ["id", "rule_results", "run_by_name", "created_at"]
        read_only_fields = fields

    def get_run_by_name(self, obj):
        return _name(obj.run_by)


class BankConfirmationSerializer(serializers.ModelSerializer):
    confirmed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BankConfirmation
        fields = ["id", "confirmed_on", "mode", "reference", "confirmed_by_name", "created_at"]
        read_only_fields = fields

    def get_confirmed_by_name(self, obj):
        return _name(obj.confirmed_by)


class QuerySerializer(serializers.ModelSerializer):
    raised_by_name = serializers.SerializerMethodField()
    days_pending = serializers.SerializerMethodField()

    class Meta:
        model = Query
        fields = ["id", "fdr_id", "message", "reply", "status", "raised_by_name", "raised_at",
                  "replied_at", "resolved_at", "days_pending"]
        read_only_fields = fields

    def get_raised_by_name(self, obj):
        return _name(obj.raised_by)

    def get_days_pending(self, obj):
        end = obj.resolved_at or timezone.now()
        return (end - obj.raised_at).days


class FdrRequestSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.SerializerMethodField()
    recommended_by_name = serializers.SerializerMethodField()
    decided_by_name = serializers.SerializerMethodField()
    fdr_number = serializers.CharField(source="fdr.fdr_number", read_only=True)

    class Meta:
        model = FdrRequest
        fields = ["id", "fdr_id", "fdr_number", "request_type", "release_kind", "reason", "status",
                  "previous_status", "bank_terms_noted", "submitted_by_name", "recommended_by_name",
                  "recommended_at", "recommendation_note", "decided_by_name", "decided_at",
                  "action_taken", "created_at"]
        read_only_fields = fields

    def get_submitted_by_name(self, obj):
        return _name(obj.submitted_by)

    def get_recommended_by_name(self, obj):
        return obj.recommended_by.name if obj.recommended_by else None

    def get_decided_by_name(self, obj):
        return obj.decided_by.name if obj.decided_by else None


class FdrSerializer(serializers.ModelSerializer):
    bank_confirmed = serializers.SerializerMethodField()
    bank_confirmed_on = serializers.SerializerMethodField()
    bank_reference = serializers.SerializerMethodField()
    institution_id = serializers.UUIDField(read_only=True)
    institution_code = serializers.CharField(source="institution.code", read_only=True)
    institution_name = serializers.CharField(source="institution.name", read_only=True)
    parent_fdr_id = serializers.UUIDField(source="parent_id", read_only=True)
    days_to_maturity = serializers.SerializerMethodField()

    class Meta:
        model = FDR
        fields = [
            "id", "fdr_number", "institution_id", "institution_code", "institution_name", "bank", "branch",
            "amount_paise", "issue_date", "maturity_date", "interest_rate", "payout_type", "category",
            "lien_marked", "held_in_favour_of_aicte", "status", "status_note", "parent_fdr_id",
            "review_flag", "days_to_maturity", "bank_confirmed", "bank_confirmed_on", "bank_reference",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_days_to_maturity(self, obj):
        return days_to_maturity(obj.maturity_date)

    def _latest_confirmation(self, obj):
        return obj.bank_confirmations.first()  # ordered newest first

    def get_bank_confirmed(self, obj):
        return self._latest_confirmation(obj) is not None

    def get_bank_confirmed_on(self, obj):
        latest = self._latest_confirmation(obj)
        return latest.confirmed_on if latest else None

    def get_bank_reference(self, obj):
        latest = self._latest_confirmation(obj)
        return latest.reference if latest else None


class FdrDetailSerializer(FdrSerializer):
    """Full record for the FDR detail page: documents, timeline, queries, renewals, reminders."""

    documents = DocumentSerializer(many=True, read_only=True)
    verification_runs = serializers.SerializerMethodField()
    bank_confirmations = BankConfirmationSerializer(many=True, read_only=True)
    queries = QuerySerializer(many=True, read_only=True)
    requests = FdrRequestSerializer(many=True, read_only=True)
    renewals = serializers.SerializerMethodField()
    reminders = serializers.SerializerMethodField()

    class Meta(FdrSerializer.Meta):
        fields = FdrSerializer.Meta.fields + [
            "documents", "verification_runs", "bank_confirmations", "queries", "requests", "renewals", "reminders",
        ]
        read_only_fields = fields

    def get_verification_runs(self, obj):
        return VerificationRunSerializer(obj.verification_runs.all()[:10], many=True).data

    def get_renewals(self, obj):
        return [{"id": str(c.pk), "fdr_number": c.fdr_number, "status": c.status} for c in obj.children.all()]

    def get_reminders(self, obj):
        logs = ReminderLog.objects.filter(fdr=obj)[:20]
        return [{"kind": log.kind, "sent_at": log.sent_at} for log in logs]


class FdrWriteSerializer(serializers.Serializer):
    fdr_number = serializers.CharField(max_length=64)
    bank = serializers.CharField(max_length=120)
    branch = serializers.CharField(max_length=120)
    amount_paise = serializers.IntegerField(min_value=1)
    issue_date = serializers.DateField()
    maturity_date = serializers.DateField()
    interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    payout_type = serializers.ChoiceField(choices=FDR.PayoutType.choices)
    category = serializers.CharField(max_length=120)
    lien_marked = serializers.BooleanField(default=False)
    held_in_favour_of_aicte = serializers.BooleanField(default=True)
    # Only administrators send this; institution users are always bound to their own institution.
    institution = serializers.PrimaryKeyRelatedField(queryset=Institution.objects.all(), required=False)

    def validate_fdr_number(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("FDR number is required.")
        return value

    def validate_bank(self, value):
        if value not in SystemSettings.load().banks:
            raise serializers.ValidationError("Choose a bank from the configured list.")
        return value

    def validate_category(self, value):
        if value not in SystemSettings.load().categories:
            raise serializers.ValidationError("Choose a category from the configured list.")
        return value

    def validate(self, attrs):
        if attrs["maturity_date"] <= attrs["issue_date"]:
            raise serializers.ValidationError({"maturity_date": "Maturity date must be after the issue date."})
        return attrs


class BankConfirmationWriteSerializer(serializers.Serializer):
    confirmed_on = serializers.DateField()
    mode = serializers.ChoiceField(choices=BankConfirmation.Mode.choices)
    reference = serializers.CharField(max_length=120)

    def validate_confirmed_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("The confirmation date cannot be in the future.")
        return value


class DecisionWriteSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["Verified", "Rejected"])
    reason = serializers.CharField(max_length=2000)


class QueryWriteSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000)


class QueryReplySerializer(serializers.Serializer):
    reply = serializers.CharField(max_length=4000)


class ReleaseRequestWriteSerializer(serializers.Serializer):
    release_kind = serializers.ChoiceField(choices=FdrRequest.ReleaseKind.choices)
    reason = serializers.CharField(max_length=2000)
    bank_terms_noted = serializers.BooleanField(default=False)


class RecommendWriteSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class RequestDecisionWriteSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approve", "reject"])
    action_taken = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
