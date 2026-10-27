from django.contrib import admin

from .models import Institution


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "state", "status")
    search_fields = ("code", "name", "state")
    list_filter = ("status", "state")
