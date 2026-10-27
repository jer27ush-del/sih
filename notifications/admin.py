from django.contrib import admin

from .models import Notification, ReminderLog


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "message", "sent_at", "read_at")
    list_filter = ("type",)


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ("key", "kind", "fdr", "sent_at")
    list_filter = ("kind",)
