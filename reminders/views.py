from rest_framework import generics

from common.policy import require

from .models import ReminderDelivery
from .serializers import ReminderDeliverySerializer


class ReminderHistoryView(generics.ListAPIView):
    """Reminder delivery history. Administrators and auditors only; institutions cannot see it."""

    serializer_class = ReminderDeliverySerializer

    def get_queryset(self):
        require(self.request.user, "view_reminders")
        qs = ReminderDelivery.objects.select_related("fdr__institution")
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs
