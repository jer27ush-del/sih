from django.urls import path

from .views import InstitutionDetailView, InstitutionListCreateView

urlpatterns = [
    path("institutions/", InstitutionListCreateView.as_view(), name="institutions"),
    path("institutions/<uuid:pk>/", InstitutionDetailView.as_view(), name="institution-detail"),
]
