import csv
import io
import uuid

from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import record_audit
from common.exceptions import BusinessRuleError
from common.policy import INSTITUTION, require, scope_fdrs
from institutions.models import Institution
from portal.models import SystemSettings

from . import services
from .documents import absolute_path
from .importer import ImportFormatError, classify, parse_csv, template_csv
from .models import FDR, Document, FdrRequest, Query
from .serializers import (
    BankConfirmationSerializer,
    BankConfirmationWriteSerializer,
    DecisionWriteSerializer,
    DocumentSerializer,
    FdrDetailSerializer,
    FdrRequestSerializer,
    FdrSerializer,
    FdrWriteSerializer,
    QueryReplySerializer,
    QuerySerializer,
    QueryWriteSerializer,
    RecommendWriteSerializer,
    ReleaseRequestWriteSerializer,
    RequestDecisionWriteSerializer,
)

ORDERING_FIELDS = {"maturity_date", "amount_paise", "created_at", "status", "fdr_number", "bank"}
ACTIVE_LIKE = [FDR.Status.ACTIVE, FDR.Status.NEARING_MATURITY, FDR.Status.MATURED,
               FDR.Status.RELEASE_REQUESTED, FDR.Status.RENEWED]


def _fdr_for(user, pk):
    """Fetch an FDR the user is allowed to see. Other institutions' records return 404."""
    return get_object_or_404(scope_fdrs(user, FDR.objects.select_related("institution")), pk=pk)


def _csv_safe(value):
    """Stop spreadsheet formula injection in exported files."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


class FdrListCreateView(generics.ListCreateAPIView):
    """GET: searchable, filterable register (scoped by role). POST: register one FDR."""

    def get_serializer_class(self):
        return FdrWriteSerializer if self.request.method == "POST" else FdrSerializer

    def get_queryset(self):
        user = self.request.user
        require(user, "view_fdrs")
        qs = scope_fdrs(user, FDR.objects.select_related("institution"))
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status__in=[s.strip() for s in p["status"].split(",") if s.strip()])
        if p.get("bank"):
            qs = qs.filter(bank__iexact=p["bank"])
        if p.get("institution"):
            qs = qs.filter(Q(institution__code__iexact=p["institution"]) | Q(institution_id=p["institution"])
                           if _is_uuid(p["institution"]) else Q(institution__code__iexact=p["institution"]))
        if p.get("maturity_from"):
            qs = qs.filter(maturity_date__gte=p["maturity_from"])
        if p.get("maturity_to"):
            qs = qs.filter(maturity_date__lte=p["maturity_to"])
        if p.get("review_flag") in ("true", "false"):
            qs = qs.filter(review_flag=p["review_flag"] == "true")
        if p.get("search"):
            term = p["search"].strip()
            qs = qs.filter(Q(fdr_number__icontains=term) | Q(bank__icontains=term)
                           | Q(institution__code__icontains=term) | Q(institution__name__icontains=term))
        order = p.get("ordering", "-created_at")
        field = order.lstrip("-")
        if field in ORDERING_FIELDS:
            qs = qs.order_by(order)
        return qs

    def create(self, request, *args, **kwargs):
        user = request.user
        require(user, "register_fdr")
        serializer = FdrWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        institution = data.pop("institution", None)
        if user.role == INSTITUTION:
            institution = user.institution
        elif institution is None:
            raise ValidationError({"institution": ["Choose the institution this FDR belongs to."]})
        fdr = services.register_fdr(data=data, institution=institution, actor=user, request=request)
        return Response(FdrDetailSerializer(fdr).data, status=201)


def _is_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


class FdrDetailView(generics.RetrieveAPIView):
    serializer_class = FdrDetailSerializer

    def get_queryset(self):
        require(self.request.user, "view_fdrs")
        return scope_fdrs(self.request.user, FDR.objects.select_related("institution", "parent"))


class DocumentListUploadView(APIView):
    def get(self, request, pk):
        require(request.user, "view_fdrs")
        fdr = _fdr_for(request.user, pk)
        return Response(DocumentSerializer(fdr.documents.all(), many=True).data)

    def post(self, request, pk):
        require(request.user, "upload_documents")
        fdr = _fdr_for(request.user, pk)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": ["Choose a PDF, PNG or JPEG file to upload."]})
        document = services.upload_document(fdr, uploaded, request.user, request)
        return Response(DocumentSerializer(document).data, status=201)


class DocumentDownloadView(APIView):
    """Files are never served directly; every download passes an access check and is audited."""

    def get(self, request, pk):
        require(request.user, "view_fdrs")
        document = get_object_or_404(Document.objects.select_related("fdr"), pk=pk)
        if not scope_fdrs(request.user, FDR.objects.filter(pk=document.fdr_id)).exists():
            raise NotFound("Document not found.")
        path = absolute_path(document)
        if not path.exists():
            raise NotFound("The file is missing from storage. Contact the administrator.")
        record_audit(action="document.downloaded", entity="Document", entity_id=document.pk,
                     actor=request.user, request=request)
        return FileResponse(open(path, "rb"), as_attachment=True, filename=document.original_name,
                            content_type=document.mime_type)


class ScreenView(APIView):
    def post(self, request, pk):
        require(request.user, "review_fdr")
        fdr = _fdr_for(request.user, pk)
        results = services.screen_fdr(fdr, request.user, request)
        return Response({"rule_results": results})


class QueryCreateView(APIView):
    def post(self, request, pk):
        require(request.user, "raise_query")
        fdr = _fdr_for(request.user, pk)
        serializer = QueryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        query = services.raise_query(fdr, request.user, serializer.validated_data["message"], request)
        return Response(QuerySerializer(query).data, status=201)


class QueryReplyView(APIView):
    def post(self, request, pk):
        require(request.user, "reply_query")
        query = get_object_or_404(Query.objects.select_related("fdr"), pk=pk)
        serializer = QueryReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        query = services.reply_to_query(query, request.user, serializer.validated_data["reply"], request)
        return Response(QuerySerializer(query).data)


class BankConfirmationView(APIView):
    def post(self, request, pk):
        require(request.user, "record_bank_confirmation")
        fdr = _fdr_for(request.user, pk)
        serializer = BankConfirmationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        confirmation = services.record_bank_confirmation(fdr, request.user, serializer.validated_data, request)
        return Response(BankConfirmationSerializer(confirmation).data, status=201)


class DecisionView(APIView):
    def post(self, request, pk):
        require(request.user, "review_fdr")
        fdr = _fdr_for(request.user, pk)
        serializer = DecisionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fdr = services.decide_fdr(fdr, request.user, data["decision"], data["reason"], request)
        return Response(FdrDetailSerializer(fdr).data)


class RenewalView(APIView):
    def post(self, request, pk):
        require(request.user, "submit_request")
        old = _fdr_for(request.user, pk)
        serializer = FdrWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("institution", None)  # a renewal always stays with the original institution
        new = services.submit_renewal(old, request.user, data, request)
        return Response(FdrDetailSerializer(new).data, status=201)


class ReleaseRequestView(APIView):
    def post(self, request, pk):
        require(request.user, "submit_request")
        fdr = _fdr_for(request.user, pk)
        serializer = ReleaseRequestWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = services.submit_release_request(fdr, request.user, serializer.validated_data, request)
        return Response(FdrRequestSerializer(req).data, status=201)


class RequestListView(generics.ListAPIView):
    serializer_class = FdrRequestSerializer

    def get_queryset(self):
        require(self.request.user, "view_fdrs")
        visible = scope_fdrs(self.request.user, FDR.objects.all())
        qs = FdrRequest.objects.filter(fdr__in=visible).select_related("fdr", "submitted_by")
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs


def _request_for(user, pk):
    req = get_object_or_404(FdrRequest.objects.select_related("fdr"), pk=pk)
    services.ensure_access(user, req.fdr)
    return req


class RequestRecommendView(APIView):
    def post(self, request, pk):
        require(request.user, "recommend_release")
        req = _request_for(request.user, pk)
        serializer = RecommendWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = services.recommend_request(req, request.user, serializer.validated_data["note"], request)
        return Response(FdrRequestSerializer(req).data)


class RequestDecisionView(APIView):
    def post(self, request, pk):
        require(request.user, "approve_release")
        req = _request_for(request.user, pk)
        serializer = RequestDecisionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        req = services.decide_request(req, request.user, data["decision"], data["action_taken"], data["reason"], request)
        return Response(FdrRequestSerializer(req).data)


class MaturityListView(generics.ListAPIView):
    """Maturity tracking: FDRs in the maturity cycle, soonest first."""

    serializer_class = FdrSerializer

    def get_queryset(self):
        require(self.request.user, "view_fdrs")
        qs = scope_fdrs(self.request.user, FDR.objects.select_related("institution"))
        return qs.filter(status__in=ACTIVE_LIKE).order_by("maturity_date")


class ImportTemplateView(APIView):
    def get(self, request):
        require(request.user, "import_fdrs")
        response = HttpResponse(template_csv(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="fdr-import-template.csv"'
        return response


class ImportView(APIView):
    """Validate a CSV first (default), then re-send with commit=true to import the valid rows.
    Add ?report=csv to download the rows that were not imported, with reasons."""

    def post(self, request):
        user = request.user
        require(user, "import_fdrs")
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": ["Choose a CSV file to upload."]})

        if user.role == INSTITUTION:
            institution = user.institution
        else:
            institution_id = request.data.get("institution")
            if not institution_id:
                raise ValidationError({"institution": ["Choose the institution for this import."]})
            institution = get_object_or_404(Institution, pk=institution_id)
        if institution.status != "Active":
            raise BusinessRuleError("This institution is inactive and cannot receive imports.")

        cfg = SystemSettings.load()
        try:
            rows = parse_csv(uploaded.read(), cfg.document_max_bytes)
        except ImportFormatError as exc:
            raise BusinessRuleError(str(exc)) from exc
        existing = {(n.lower(), b.lower()) for n, b in FDR.objects.values_list("fdr_number", "bank")}
        classify(rows, existing, cfg.banks, cfg.categories)

        if request.query_params.get("report") == "csv":
            return _error_report(rows)

        commit = str(request.data.get("commit", "false")).lower() in ("true", "1", "yes")
        if commit:
            if not any(row["status"] == "valid" for row in rows):
                raise BusinessRuleError("There are no valid rows to import.")
            created = services.bulk_import(rows, institution, user, request)
            return Response({"created": len(created), "skipped": len(rows) - len(created), "fdr_ids": created},
                            status=201)

        summary = {status: sum(1 for r in rows if r["status"] == status) for status in ("valid", "error", "duplicate")}
        preview = [
            {"line": r["line"], "status": r["status"], "fdr_number": r["raw"].get("fdr_number", ""),
             "messages": r["errors"] or [r.get("reason", "")]}
            for r in rows
        ]
        return Response({"summary": summary, "rows": preview})


def _error_report(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["line", "status", "fdr_number", "reason"])
    for row in rows:
        if row["status"] == "valid":
            continue
        reason = "; ".join(row["errors"]) if row["errors"] else row.get("reason", "")
        writer.writerow([row["line"], row["status"], _csv_safe(row["raw"].get("fdr_number", "")), _csv_safe(reason)])
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="fdr-import-errors.csv"'
    return response
