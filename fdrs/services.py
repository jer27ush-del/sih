"""Business operations for FDRs. Each function is one workflow action. Each one:
  1. checks the actor's role (common/policy.py),
  2. locks the affected rows,
  3. checks the state (fdrs/workflow.py),
  4. makes the change and writes the audit entry in the same transaction.
Views only parse requests and call these functions."""
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from audit.services import record_audit
from common.exceptions import BusinessRuleError, ConflictError
from common.policy import INSTITUTION, can_approve_release, is_own_institution, require
from notifications.services import administrators, institution_users, notify, officers
from portal.models import SystemSettings

from .documents import store_document
from .models import FDR, BankConfirmation, FdrRequest, Query, VerificationRun
from .rules import run_rules
from .workflow import change_status

S = FDR.Status
RT = FdrRequest.RequestType
RK = FdrRequest.ReleaseKind
RS = FdrRequest.Status
UPLOADABLE_STATES = {S.SUBMITTED, S.UNDER_VERIFICATION, S.QUERY_RAISED, S.CORRECTED}
CONFIRMABLE_STATES = {S.UNDER_VERIFICATION, S.QUERY_RAISED, S.CORRECTED}
RELEASABLE_STATES = {S.ACTIVE, S.NEARING_MATURITY, S.MATURED}
OPEN_REQUEST_MESSAGE = "An open request already exists for this FDR."


def lock_fdr(pk):
    return FDR.objects.select_for_update().select_related("institution").get(pk=pk)


def ensure_access(user, fdr):
    """Institution users get 404 (not 403) for other institutions' records, so existence is not leaked."""
    if not is_own_institution(user, fdr.institution_id):
        raise NotFound("FDR not found.")


def fdr_snapshot(fdr):
    return {
        "fdr_number": fdr.fdr_number, "bank": fdr.bank, "branch": fdr.branch,
        "amount_paise": fdr.amount_paise, "issue_date": fdr.issue_date.isoformat(),
        "maturity_date": fdr.maturity_date.isoformat(), "institution_id": str(fdr.institution_id),
        "parent_id": str(fdr.parent_id) if fdr.parent_id else None, "status": fdr.status,
    }


def ensure_not_duplicate(fdr_number, bank):
    if FDR.objects.filter(fdr_number__iexact=fdr_number.strip(), bank__iexact=bank.strip()).exists():
        raise ConflictError("This FDR number already exists for this bank.")


def has_open_request(fdr):
    return fdr.requests.filter(status__in=FdrRequest.OPEN_STATUSES).exists()


def run_screening(fdr, actor=None, request=None, audit=True):
    """Run the seven automated checks and store the result as history."""
    cfg = SystemSettings.load()
    documents = [
        {"mime_type": d.mime_type, "size_bytes": d.size_bytes, "active": d.active, "scan_status": d.scan_status}
        for d in fdr.documents.all()
    ]
    duplicate_exists = (
        FDR.objects.filter(fdr_number__iexact=fdr.fdr_number, bank__iexact=fdr.bank).exclude(pk=fdr.pk).exists()
    )
    results = run_rules(
        fdr_number=fdr.fdr_number, bank=fdr.bank, branch=fdr.branch, amount_paise=fdr.amount_paise,
        issue_date=fdr.issue_date, maturity_date=fdr.maturity_date, documents=documents,
        duplicate_exists=duplicate_exists, bank_confirmed=fdr.bank_confirmations.exists(),
        allowed_mime_types=cfg.allowed_document_types, minimum_tenure_days=cfg.minimum_tenure_days,
        amount_min_paise=cfg.amount_min_paise, amount_max_paise=cfg.amount_max_paise,
    )
    VerificationRun.objects.create(fdr=fdr, rule_results=results, run_by=actor)
    fdr.review_flag = any(flag != "pass" for name, flag in results.items() if name != "bank_confirmation")
    fdr.save(update_fields=["review_flag", "updated_at"])
    if audit:
        record_audit(
            action="fdr.screened", entity="FDR", entity_id=fdr.pk, actor=actor,
            new={"review_flag": fdr.review_flag, "results": results}, request=request,
        )
    return results


def _create_fdr(data, institution, actor, *, parent=None, request=None, audit=True):
    try:
        with transaction.atomic():
            fdr = FDR.objects.create(
                institution=institution, submitted_by=actor, parent=parent, status=S.SUBMITTED, **data
            )
    except IntegrityError as exc:
        raise ConflictError("This FDR number already exists for this bank.") from exc
    if audit:
        record_audit(action="fdr.submitted", entity="FDR", entity_id=fdr.pk, actor=actor,
                     new=fdr_snapshot(fdr), request=request)
    change_status(fdr, S.UNDER_VERIFICATION, None, note="Automated checks started", request=request, audit=audit)
    run_screening(fdr, actor=None, request=request, audit=audit)
    return fdr


def register_fdr(*, data, institution, actor, request=None):
    require(actor, "register_fdr")
    if actor.role == INSTITUTION and not is_own_institution(actor, institution.pk):
        raise PermissionDenied("You can register FDRs only for your own institution.")
    if institution.status != "Active":
        raise BusinessRuleError("This institution is inactive and cannot register new FDRs.")
    ensure_not_duplicate(data["fdr_number"], data["bank"])
    with transaction.atomic():
        return _create_fdr(data, institution, actor, request=request)


def bulk_import(rows, institution, actor, request=None):
    """Imports only the rows marked valid, as one audit batch."""
    require(actor, "import_fdrs")
    created = []
    with transaction.atomic():
        for row in rows:
            if row["status"] == "valid":
                fdr = _create_fdr(row["data"], institution, actor, request=request, audit=False)
                created.append(str(fdr.pk))
        skipped = len(rows) - len(created)
        record_audit(
            action="fdr.bulk_import", entity="ImportBatch", entity_id=uuid.uuid4(), actor=actor,
            new={"institution_id": str(institution.pk), "created": len(created), "skipped": skipped,
                 "fdr_ids": created},
            request=request,
        )
    return created


def upload_document(fdr, uploaded, actor, request=None):
    require(actor, "upload_documents")
    ensure_access(actor, fdr)
    if fdr.status not in UPLOADABLE_STATES:
        raise BusinessRuleError("Documents can be uploaded only before verification is complete.")
    with transaction.atomic():
        doc = store_document(fdr, uploaded, actor)
        record_audit(
            action="document.uploaded", entity="Document", entity_id=doc.pk, actor=actor, request=request,
            new={"fdr_id": str(fdr.pk), "version": doc.version, "sha256": doc.sha256,
                 "original_name": doc.original_name, "scan_status": doc.scan_status},
        )
        run_screening(fdr, actor=actor, request=request)
    return doc


def screen_fdr(fdr, actor, request=None):
    require(actor, "review_fdr")
    with transaction.atomic():
        fdr = lock_fdr(fdr.pk)
        if fdr.status == S.CORRECTED:
            change_status(fdr, S.UNDER_VERIFICATION, actor, note="Re-review after institution response", request=request)
        elif fdr.status != S.UNDER_VERIFICATION:
            raise BusinessRuleError("Automated checks can run only while a record is under verification.")
        return run_screening(fdr, actor=actor, request=request)


def raise_query(fdr, actor, message, request=None):
    require(actor, "raise_query")
    with transaction.atomic():
        fdr = lock_fdr(fdr.pk)
        if fdr.status != S.UNDER_VERIFICATION:
            raise BusinessRuleError("Queries can be raised only while a record is under verification.")
        query = Query.objects.create(fdr=fdr, raised_by=actor, message=message)
        change_status(fdr, S.QUERY_RAISED, actor, note=message, request=request)
        record_audit(action="query.raised", entity="Query", entity_id=query.pk, actor=actor,
                     new={"fdr_id": str(fdr.pk), "message": message}, request=request)
        notify(institution_users(fdr.institution_id), type="query",
               message=f"Query raised on {fdr.fdr_number}: {message[:200]}", link=f"/fdrs/{fdr.pk}")
    return query


def reply_to_query(query, actor, reply, request=None):
    require(actor, "reply_query")
    with transaction.atomic():
        query = Query.objects.select_related("fdr").get(pk=query.pk)
        ensure_access(actor, query.fdr)
        fdr = lock_fdr(query.fdr_id)
        if query.status != Query.Status.OPEN:
            raise BusinessRuleError("This query has already been answered.")
        if fdr.status != S.QUERY_RAISED:
            raise BusinessRuleError("This record is not waiting for a reply.")
        now = timezone.now()
        query.reply, query.replied_at = reply, now
        query.status, query.resolved_at = Query.Status.RESOLVED, now
        query.save()
        change_status(fdr, S.CORRECTED, actor, note=reply, request=request)
        record_audit(action="query.replied", entity="Query", entity_id=query.pk, actor=actor,
                     new={"reply": reply[:500]}, request=request)
        notify(officers(), type="query_reply",
               message=f"Institution replied to the query on {fdr.fdr_number}", link=f"/fdrs/{fdr.pk}")
    return query


def record_bank_confirmation(fdr, actor, data, request=None):
    require(actor, "record_bank_confirmation")
    with transaction.atomic():
        fdr = lock_fdr(fdr.pk)
        if fdr.status not in CONFIRMABLE_STATES:
            raise BusinessRuleError("Bank confirmation can be recorded while the record is being verified.")
        confirmation = BankConfirmation.objects.create(fdr=fdr, confirmed_by=actor, **data)
        record_audit(
            action="bank.confirmed", entity="BankConfirmation", entity_id=confirmation.pk, actor=actor,
            new={"fdr_id": str(fdr.pk), "confirmed_on": data["confirmed_on"].isoformat(),
                 "mode": data["mode"], "reference": data["reference"]},
            request=request,
        )
    return confirmation


def _complete_renewal(new_fdr, request=None):
    old = lock_fdr(new_fdr.parent_id)
    if old.status == S.RENEWED:
        change_status(old, S.RELEASED_CLOSED, None, note=f"Replaced by {new_fdr.fdr_number}", request=request)
    renewal = old.requests.filter(request_type=RT.RENEWAL, status=RS.SUBMITTED).first()
    if renewal:
        renewal.status, renewal.decided_at = RS.COMPLETED, timezone.now()
        renewal.save(update_fields=["status", "decided_at"])
        record_audit(action="request.renewal.completed", entity="FdrRequest", entity_id=renewal.pk,
                     new={"status": RS.COMPLETED}, request=request)


def decide_fdr(fdr, actor, decision, reason, request=None):
    """Final officer decision. Verified requires a recorded bank confirmation and a usable document."""
    require(actor, "review_fdr")
    with transaction.atomic():
        fdr = lock_fdr(fdr.pk)
        if fdr.status != S.UNDER_VERIFICATION:
            raise BusinessRuleError("Only a record under verification can be verified or rejected.")
        if decision == "Rejected":
            change_status(fdr, S.REJECTED, actor, note=reason, request=request)
            notify(institution_users(fdr.institution_id), type="rejected",
                   message=f"{fdr.fdr_number} was rejected: {reason[:200]}", link=f"/fdrs/{fdr.pk}")
            return fdr

        if not fdr.bank_confirmations.exists():
            raise BusinessRuleError("Record bank confirmation before verifying this FDR.")
        if not fdr.documents.filter(active=True, scan_status__in=["clean", "unscanned"]).exists():
            raise BusinessRuleError("Attach a usable supporting document before verifying this FDR.")
        change_status(fdr, S.VERIFIED, actor, note=reason, request=request)
        change_status(fdr, S.ACTIVE, None, note="Verified; now active", request=request)
        if fdr.parent_id:
            _complete_renewal(fdr, request)
        notify(institution_users(fdr.institution_id), type="verified",
               message=f"{fdr.fdr_number} has been verified and is active.", link=f"/fdrs/{fdr.pk}")
    return fdr


def submit_renewal(old, actor, data, request=None):
    """Creates the replacement FDR, links it to the old one, and marks the old one Renewed."""
    require(actor, "submit_request")
    ensure_access(actor, old)
    with transaction.atomic():
        old = lock_fdr(old.pk)
        if old.status not in (S.NEARING_MATURITY, S.MATURED):
            raise BusinessRuleError("A renewal can be submitted only when the FDR is nearing or past maturity.")
        if old.children.exists():
            raise ConflictError("A replacement FDR has already been submitted for this deposit.")
        if has_open_request(old):
            raise BusinessRuleError(OPEN_REQUEST_MESSAGE)
        ensure_not_duplicate(data["fdr_number"], data["bank"])
        new = _create_fdr(data, old.institution, actor, parent=old, request=request)
        FdrRequest.objects.create(
            fdr=old, request_type=RT.RENEWAL, reason=f"Replacement FDR {new.fdr_number}",
            status=RS.SUBMITTED, submitted_by=actor,
        )
        change_status(old, S.RENEWED, actor, note=f"Replacement FDR {new.fdr_number} submitted", request=request)
        notify(officers(), type="renewal", message=f"Renewal submitted for {old.fdr_number}",
               link=f"/fdrs/{new.pk}")
    return new


def submit_release_request(fdr, actor, data, request=None):
    require(actor, "submit_request")
    ensure_access(actor, fdr)
    with transaction.atomic():
        fdr = lock_fdr(fdr.pk)
        if fdr.status not in RELEASABLE_STATES:
            raise BusinessRuleError("A release can be requested only for an active or matured FDR.")
        kind = data["release_kind"]
        if kind == RK.AT_MATURITY and fdr.status != S.MATURED:
            raise BusinessRuleError(
                "Release at maturity can be requested once the FDR has matured. "
                "For an earlier release, use premature withdrawal."
            )
        if kind == RK.PREMATURE and not data.get("bank_terms_noted"):
            raise BusinessRuleError("Confirm that the bank's premature-closure terms have been noted.")
        if has_open_request(fdr):
            raise BusinessRuleError(OPEN_REQUEST_MESSAGE)
        if not fdr.documents.filter(active=True).exists():
            raise BusinessRuleError("Attach the required supporting documents before submitting a release request.")

        previous = fdr.status
        req = FdrRequest.objects.create(
            fdr=fdr, request_type=RT.RELEASE, release_kind=kind, reason=data["reason"],
            status=RS.SUBMITTED, previous_status=previous,
            bank_terms_noted=bool(data.get("bank_terms_noted")), submitted_by=actor,
        )
        change_status(fdr, S.RELEASE_REQUESTED, actor, note=f"Release request: {kind}", request=request)
        record_audit(action="request.release.submitted", entity="FdrRequest", entity_id=req.pk, actor=actor,
                     new={"fdr_id": str(fdr.pk), "release_kind": kind, "reason": data["reason"][:500]},
                     request=request)
        notify(officers(), type="release_request",
               message=f"Release request submitted for {fdr.fdr_number}", link=f"/requests/{req.pk}")
    return req


def recommend_request(req, actor, note, request=None):
    require(actor, "recommend_release")
    with transaction.atomic():
        req = FdrRequest.objects.select_for_update().get(pk=req.pk)
        if req.request_type != RT.RELEASE or req.status != RS.SUBMITTED:
            raise BusinessRuleError("Only a submitted release request can be recommended.")
        if actor.pk == req.submitted_by_id:
            raise PermissionDenied("You cannot recommend a request you submitted.")
        req.status = RS.RECOMMENDED
        req.recommended_by, req.recommended_at = actor, timezone.now()
        req.recommendation_note = note
        req.save()
        record_audit(action="request.recommended", entity="FdrRequest", entity_id=req.pk, actor=actor,
                     new={"status": RS.RECOMMENDED}, request=request)
        notify(administrators(), type="release_recommended",
               message="A release request is ready for final approval", link=f"/requests/{req.pk}")
    return req


def decide_request(req, actor, decision, action_taken, reason, request=None):
    """Final approval or rejection. Separation of duties is enforced here, not in the UI."""
    require(actor, "approve_release")
    with transaction.atomic():
        req = FdrRequest.objects.select_for_update().get(pk=req.pk)
        if req.request_type != RT.RELEASE or req.status != RS.RECOMMENDED:
            raise BusinessRuleError("Only a recommended release request can be decided.")
        if not can_approve_release(actor, req):
            raise PermissionDenied(
                "Separation of duties: the approver cannot be the person who submitted or recommended this request."
            )
        fdr = lock_fdr(req.fdr_id)
        now = timezone.now()
        req.decided_by, req.decided_at = actor, now
        if decision == "approve":
            if not (action_taken or "").strip():
                raise BusinessRuleError("Record the action taken before approving.")
            req.status, req.action_taken = RS.APPROVED, action_taken.strip()
            change_status(fdr, S.RELEASED_CLOSED, actor, note=req.action_taken, request=request)
        else:
            if not (reason or "").strip():
                raise BusinessRuleError("A reason is required to reject a request.")
            req.status, req.action_taken = RS.REJECTED, reason.strip()
            change_status(fdr, req.previous_status, actor, note=reason.strip(), request=request)
        req.save()
        record_audit(action=f"request.release.{'approved' if decision == 'approve' else 'rejected'}",
                     entity="FdrRequest", entity_id=req.pk, actor=actor,
                     new={"status": req.status, "action_taken": req.action_taken}, request=request)
        notify(institution_users(fdr.institution_id), type="release_decided",
               message=f"The release request for {fdr.fdr_number} was {req.status.lower()}",
               link=f"/fdrs/{fdr.pk}")
    return req
