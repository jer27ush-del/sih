from django.contrib import admin
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.urls import include, path, re_path

from config.views import spa_index


def health(request):
    """Health check for Render and uptime monitors."""
    try:
        connection.ensure_connection()
    except Exception:  # noqa: BLE001 - any failure means the database is unreachable
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/", include("accounts.urls")),
    path("api/", include("institutions.urls")),
    path("api/", include("fdrs.urls")),
    path("api/", include("notifications.urls")),
    path("api/", include("audit.urls")),
    path("api/", include("reminders.urls")),
    path("api/", include("portal.urls")),
    # Everything else (the React app's pages) is served by the built single-page app.
    re_path(r"^(?!api/|admin/|static/|media/).*$", spa_index, name="spa"),
]
