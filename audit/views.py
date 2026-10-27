from rest_framework import generics

from common.policy import OFFICER, require

from .models import AuditLog
from .serializers import AuditLogSerializer

# Officers see only review-related history, per the permission matrix ("Limited").
OFFICER_VISIBLE_ENTITIES = {"FDR", "Query", "FdrRequest", "BankConfirmation", "VerificationRun", "Document"}


class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == OFFICER:
            require(user, "view_limited_audit_logs")
        else:
            require(user, "view_audit_logs")

        qs = AuditLog.objects.select_related("actor")
        if user.role == OFFICER:
            qs = qs.filter(entity__in=OFFICER_VISIBLE_ENTITIES)

        params = self.request.query_params
        if params.get("entity"):
            qs = qs.filter(entity=params["entity"])
        if params.get("action"):
            qs = qs.filter(action__icontains=params["action"])
        if params.get("entity_id"):
            qs = qs.filter(entity_id=params["entity_id"])
        if params.get("from"):
            qs = qs.filter(timestamp__date__gte=params["from"])
        if params.get("to"):
            qs = qs.filter(timestamp__date__lte=params["to"])
        return qs
