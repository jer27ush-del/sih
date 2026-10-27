from django.urls import path

from . import views

urlpatterns = [
    path("fdrs/", views.FdrListCreateView.as_view(), name="fdrs"),
    path("fdrs/import/", views.ImportView.as_view(), name="fdr-import"),
    path("fdrs/import/template/", views.ImportTemplateView.as_view(), name="fdr-import-template"),
    path("fdrs/<uuid:pk>/", views.FdrDetailView.as_view(), name="fdr-detail"),
    path("fdrs/<uuid:pk>/documents/", views.DocumentListUploadView.as_view(), name="fdr-documents"),
    path("documents/<uuid:pk>/download/", views.DocumentDownloadView.as_view(), name="document-download"),
    path("fdrs/<uuid:pk>/verify/", views.ScreenView.as_view(), name="fdr-verify"),
    path("fdrs/<uuid:pk>/queries/", views.QueryCreateView.as_view(), name="fdr-queries"),
    path("queries/<uuid:pk>/reply/", views.QueryReplyView.as_view(), name="query-reply"),
    path("fdrs/<uuid:pk>/bank-confirmation/", views.BankConfirmationView.as_view(), name="fdr-bank-confirmation"),
    path("fdrs/<uuid:pk>/decision/", views.DecisionView.as_view(), name="fdr-decision"),
    path("fdrs/<uuid:pk>/renewals/", views.RenewalView.as_view(), name="fdr-renewals"),
    path("fdrs/<uuid:pk>/requests/", views.ReleaseRequestView.as_view(), name="fdr-requests"),
    path("requests/", views.RequestListView.as_view(), name="requests"),
    path("requests/<uuid:pk>/recommend/", views.RequestRecommendView.as_view(), name="request-recommend"),
    path("requests/<uuid:pk>/decision/", views.RequestDecisionView.as_view(), name="request-decision"),
    path("maturity/", views.MaturityListView.as_view(), name="maturity"),
]
