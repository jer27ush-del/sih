from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    """Users only ever see their own inbox."""

    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") == "true":
            qs = qs.filter(read_at__isnull=True)
        return qs


class NotificationReadView(APIView):
    def patch(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        if request.data.get("read", True):
            notification.read_at = notification.read_at or timezone.now()
        else:
            notification.read_at = None
        notification.save(update_fields=["read_at"])
        return Response(NotificationSerializer(notification).data)
