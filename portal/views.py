import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import record_audit
from common.exceptions import BusinessRuleError, FeatureUnavailableError
from common.policy import require, scope_fdrs
from fdrs.models import FDR, FdrRequest, Query
from fdrs.serializers import FdrSerializer

from .models import SystemSettings
from .serializers import SETTING_FIELDS, SystemSettingsSerializer

S = FDR.Status
ACTIVE_SET = [S.ACTIVE, S.NEARING_MATURITY, S.MATURED, S.RENEWED, S.RELEASE_REQUESTED]
PENDING_SET = [S.SUBMITTED, S.UNDER_VERIFICATION, S.CORRECTED]


class SettingsView(APIView):
    """Administrator-only configuration: reminder thresholds, document limits, bank and category lists."""

    def get(self, request):
        require(request.user, "change_settings")
        return Response(SystemSettingsSerializer(SystemSettings.load()).data)

    def put(self, request):
        return self._save(request, partial=False)

    def patch(self, request):
        return self._save(request, partial=True)

    def _save(self, request, partial):
        require(request.user, "change_settings")
        instance = SystemSettings.load()
        old = {field: getattr(instance, field) for field in SETTING_FIELDS}
        serializer = SystemSettingsSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(updated_by=request.user)
        record_audit(action="settings.updated", entity="Settings", entity_id="global", actor=request.user,
                     old=old, new=serializer.data, request=request)
        return Response(SystemSettingsSerializer(instance).data)


class SettingsOptionsView(APIView):
    """Lists every signed-in user needs for forms (banks, categories, upload limits)."""

    def get(self, request):
        cfg = SystemSettings.load()
        return Response({
            "banks": cfg.banks,
            "categories": cfg.categories,
            "allowed_document_types": cfg.allowed_document_types,
            "document_max_bytes": cfg.document_max_bytes,
            "minimum_tenure_days": cfg.minimum_tenure_days,
            "amount_limits_paise": {"min": cfg.amount_min_paise, "max": cfg.amount_max_paise},
            "maturity_thresholds": cfg.maturity_thresholds,
        })


class DashboardSummaryView(APIView):
    """Every figure is calculated from the database at request time. Nothing is hardcoded."""

    def get(self, request):
        require(request.user, "view_dashboard")
        today = timezone.localdate()
        fdrs = scope_fdrs(request.user, FDR.objects.all())
        totals = fdrs.aggregate(count=Count("id"), value=Sum("amount_paise"))

        def maturing_within(days):
            return fdrs.filter(status__in=ACTIVE_SET, maturity_date__gte=today,
                               maturity_date__lte=today + timedelta(days=days)).count()

        data = {
            "total_fdrs": totals["count"] or 0,
            "total_deposit_paise": totals["value"] or 0,
            "active_fdrs": fdrs.filter(status__in=ACTIVE_SET).count(),
            "maturing_30_days": maturing_within(30),
            "maturing_60_days": maturing_within(60),
            "maturing_90_days": maturing_within(90),
            "overdue_unactioned": fdrs.filter(status=S.MATURED).count(),
            "pending_verification": fdrs.filter(status__in=PENDING_SET).count(),
            "open_queries": Query.objects.filter(status=Query.Status.OPEN, fdr__in=fdrs).count(),
            "flagged_for_review": fdrs.filter(review_flag=True).count(),
            "pending_requests": FdrRequest.objects.filter(
                fdr__in=fdrs, status__in=FdrRequest.OPEN_STATUSES).count(),
            "status_breakdown": list(fdrs.values("status").annotate(count=Count("id")).order_by("status")),
            "recent_submissions": FdrSerializer(fdrs.select_related("institution")[:5], many=True).data,
            "upcoming_maturities": FdrSerializer(
                fdrs.select_related("institution").filter(status__in=ACTIVE_SET, maturity_date__gte=today)
                .order_by("maturity_date")[:5], many=True).data,
        }
        return Response(data)


def _rupees(paise):
    return str((Decimal(paise) / Decimal(100)).quantize(Decimal("0.01")))


def _filter_fdrs(qs, params):
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    if params.get("bank"):
        qs = qs.filter(bank__iexact=params["bank"])
    if params.get("institution"):
        qs = qs.filter(institution__code__iexact=params["institution"])
    return qs


def _register(user, params):
    qs = _filter_fdrs(scope_fdrs(user, FDR.objects.select_related("institution")), params)
    columns = ["FDR number", "Institution code", "Institution", "Bank", "Branch", "Amount (INR)",
               "Issue date", "Maturity date", "Status", "Review flag"]
    rows = [[f.fdr_number, f.institution.code, f.institution.name, f.bank, f.branch, _rupees(f.amount_paise),
             f.issue_date.isoformat(), f.maturity_date.isoformat(), f.status, "Yes" if f.review_flag else "No"]
            for f in qs]
    return columns, rows


def _upcoming(user, params):
    today = timezone.localdate()
    days = int(params.get("days", 90))
    qs = _filter_fdrs(scope_fdrs(user, FDR.objects.select_related("institution")), params).filter(
        status__in=ACTIVE_SET, maturity_date__gte=today, maturity_date__lte=today + timedelta(days=days))
    columns = ["FDR number", "Institution code", "Bank", "Amount (INR)", "Maturity date", "Days remaining"]
    rows = [[f.fdr_number, f.institution.code, f.bank, _rupees(f.amount_paise), f.maturity_date.isoformat(),
             (f.maturity_date - today).days] for f in qs.order_by("maturity_date")]
    return columns, rows


def _overdue(user, params):
    today = timezone.localdate()
    qs = _filter_fdrs(scope_fdrs(user, FDR.objects.select_related("institution")), params).filter(
        status=S.MATURED).exclude(requests__status__in=FdrRequest.OPEN_STATUSES)
    columns = ["FDR number", "Institution code", "Bank", "Amount (INR)", "Maturity date", "Days overdue"]
    rows = [[f.fdr_number, f.institution.code, f.bank, _rupees(f.amount_paise), f.maturity_date.isoformat(),
             (today - f.maturity_date).days] for f in qs.order_by("maturity_date")]
    return columns, rows


def _pending(user, params):
    today = timezone.localdate()
    qs = _filter_fdrs(scope_fdrs(user, FDR.objects.select_related("institution")), params).filter(
        status__in=PENDING_SET)
    columns = ["FDR number", "Institution code", "Bank", "Status", "Days pending"]
    rows = [[f.fdr_number, f.institution.code, f.bank, f.status, (today - f.created_at.date()).days]
            for f in qs.order_by("created_at")]
    return columns, rows


def _open_queries(user, params):
    now = timezone.now()
    qs = Query.objects.select_related("fdr__institution").filter(
        status=Query.Status.OPEN, fdr__in=scope_fdrs(user, FDR.objects.all()))
    columns = ["FDR number", "Institution code", "Query", "Raised on", "Days pending"]
    rows = [[q.fdr.fdr_number, q.fdr.institution.code, q.message, q.raised_at.date().isoformat(),
             (now - q.raised_at).days] for q in qs.order_by("raised_at")]
    return columns, rows


def _requests(user, params):
    visible = scope_fdrs(user, FDR.objects.all())
    qs = FdrRequest.objects.select_related("fdr").filter(fdr__in=visible)
    columns = ["FDR number", "Type", "Status", "Reason", "Submitted on"]
    rows = [[r.fdr.fdr_number, r.request_type, r.status, r.reason, r.created_at.date().isoformat()]
            for r in qs.order_by("-created_at")]
    return columns, rows


def _bank_summary(user, params):
    qs = scope_fdrs(user, FDR.objects.all())
    columns = ["Bank", "FDR count", "Total (INR)"]
    rows = [[row["bank"], row["count"], _rupees(row["value"] or 0)]
            for row in qs.values("bank").annotate(count=Count("id"), value=Sum("amount_paise")).order_by("bank")]
    return columns, rows


def _institution_summary(user, params):
    qs = scope_fdrs(user, FDR.objects.select_related("institution"))
    columns = ["Institution code", "Institution", "FDR count", "Total (INR)"]
    grouped = qs.values("institution__code", "institution__name").annotate(
        count=Count("id"), value=Sum("amount_paise")).order_by("institution__code")
    rows = [[g["institution__code"], g["institution__name"], g["count"], _rupees(g["value"] or 0)] for g in grouped]
    return columns, rows


REPORTS = {
    "fdr-register": _register,
    "upcoming-maturities": _upcoming,
    "overdue-maturities": _overdue,
    "pending-verification": _pending,
    "open-queries": _open_queries,
    "requests": _requests,
    "bank-summary": _bank_summary,
    "institution-summary": _institution_summary,
}


def _safe(value):
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


class ReportView(APIView):
    """Reports respect the viewer's role. CSV is available; PDF is planned and reports 501 for now."""

    def get(self, request, name):
        require(request.user, "view_reports")
        builder = REPORTS.get(name)
        if builder is None:
            raise NotFound("Unknown report.")
        fmt = request.query_params.get("format", "json")
        if fmt == "pdf":
            raise FeatureUnavailableError("PDF export is not available in this release. Use format=csv.")
        if fmt not in ("json", "csv"):
            raise BusinessRuleError("Format must be json or csv.")

        columns, rows = builder(request.user, request.query_params)
        record_audit(action="report.exported", entity="Report", entity_id=name, actor=request.user,
                     new={"format": fmt, "rows": len(rows), "filters": dict(request.query_params)},
                     request=request)
        if fmt == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns)
            for row in rows:
                writer.writerow([_safe(cell) for cell in row])
            response = HttpResponse(buffer.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="{name}.csv"'
            return response
        return Response({"name": name, "columns": columns, "rows": rows})
