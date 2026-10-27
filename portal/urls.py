from django.urls import path

from . import views

urlpatterns = [
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path("settings/options/", views.SettingsOptionsView.as_view(), name="settings-options"),
    path("dashboard/summary/", views.DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("reports/<str:name>/", views.ReportView.as_view(), name="report"),
]
