from django.db.models import Q
from rest_framework import generics
from rest_framework.response import Response

from audit.services import record_audit
from common.policy import require

from .models import Institution
from .serializers import InstitutionSerializer


class InstitutionListCreateView(generics.ListCreateAPIView):
    serializer_class = InstitutionSerializer

    def get_queryset(self):
        require(self.request.user, "view_institutions")
        qs = Institution.objects.all()
        params = self.request.query_params
        if params.get("search"):
            term = params["search"].strip()
            qs = qs.filter(Q(code__icontains=term) | Q(name__icontains=term) | Q(state__icontains=term))
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs

    def create(self, request, *args, **kwargs):
        require(request.user, "manage_institutions")  # check before validating the body
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        institution = serializer.save()
        record_audit(
            actor=request.user, action="institution.created", entity="Institution", entity_id=institution.id,
            new=serializer.data, request=request,
        )
        return Response(serializer.data, status=201)


class InstitutionDetailView(generics.RetrieveUpdateAPIView):
    """Institutions are edited or deactivated (status = Inactive), never hard-deleted."""

    serializer_class = InstitutionSerializer

    def get_queryset(self):
        require(self.request.user, "view_institutions")
        return Institution.objects.all()

    def update(self, request, *args, **kwargs):
        require(request.user, "manage_institutions")
        instance = self.get_object()
        old = InstitutionSerializer(instance).data
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        action = "institution.deactivated" if serializer.instance.status == "Inactive" and old["status"] == "Active" else "institution.updated"
        record_audit(
            actor=request.user, action=action, entity="Institution", entity_id=instance.id,
            old=old, new=serializer.data, request=request,
        )
        return Response(serializer.data)
