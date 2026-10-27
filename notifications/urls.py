from django.urls import path

from .views import NotificationListView, NotificationReadView

urlpatterns = [
    path("notifications/", NotificationListView.as_view(), name="notifications"),
    path("notifications/<uuid:pk>/", NotificationReadView.as_view(), name="notification-read"),
]
