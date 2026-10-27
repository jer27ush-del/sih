from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["id", "timestamp", "actor_label", "action", "entity", "entity_id", "old_value", "new_value", "ip_address"]
        read_only_fields = fields
