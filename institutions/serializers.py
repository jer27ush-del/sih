from rest_framework import serializers

from .models import Institution


class InstitutionSerializer(serializers.ModelSerializer):
    fdr_count = serializers.SerializerMethodField()

    class Meta:
        model = Institution
        fields = [
            "id", "code", "name", "state", "contact_name", "email", "phone",
            "status", "fdr_count", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "fdr_count", "created_at", "updated_at"]

    def get_fdr_count(self, obj):
        return obj.fdrs.count()

    def validate_code(self, value):
        value = value.strip()
        qs = Institution.objects.filter(code__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An institution with this code already exists.")
        return value
