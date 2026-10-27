from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Users are normally created through the API (which sends a set-password link).
    The admin shows the account but never displays or edits password hashes."""

    list_display = ("email", "name", "role", "institution", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("email", "name")
    readonly_fields = ("password", "last_login", "created_at")
    exclude = ("groups", "user_permissions")
