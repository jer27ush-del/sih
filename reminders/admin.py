from django.contrib import admin

from .models import ReminderDelivery


@admin.register(ReminderDelivery)
class ReminderDeliveryAdmin(admin.ModelAdmin):
    list_display = ("fdr", "reminder_days", "maturity_date", "recipient", "status", "attempts", "accepted_at")
    list_filter = ("status", "reminder_days")
    search_fields = ("fdr__fdr_number", "recipient")
    readonly_fields = [f.name for f in ReminderDelivery._meta.fields]

    def has_add_permission(self, request):
        return False
