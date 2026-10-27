from django.urls import path

from .views import ReminderHistoryView

urlpatterns = [
    path("reminders/", ReminderHistoryView.as_view(), name="reminder-history"),
]
