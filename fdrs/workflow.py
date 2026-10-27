"""The FDR status machine (Section 4). Every status change goes through change_status(),
which checks the allowed transition and the actor's role, then writes the audit entry
in the same transaction."""
from rest_framework.exceptions import PermissionDenied

from audit.services import record_audit
from common.exceptions import BusinessRuleError
from common.policy import ADMIN, INSTITUTION, OFFICER

from .models import FDR

SYSTEM = "system"
S = FDR.Status

# (from, to) -> roles allowed to trigger it. "system" means scheduled jobs or automatic steps.
ALLOWED = {
    (S.SUBMITTED, S.UNDER_VERIFICATION): {SYSTEM},
    (S.UNDER_VERIFICATION, S.QUERY_RAISED): {OFFICER, ADMIN},
    (S.UNDER_VERIFICATION, S.VERIFIED): {OFFICER, ADMIN},
    (S.UNDER_VERIFICATION, S.REJECTED): {OFFICER, ADMIN},
    (S.QUERY_RAISED, S.CORRECTED): {INSTITUTION, ADMIN},
    (S.CORRECTED, S.UNDER_VERIFICATION): {OFFICER, ADMIN},
    (S.VERIFIED, S.ACTIVE): {SYSTEM},
    (S.ACTIVE, S.NEARING_MATURITY): {SYSTEM},
    (S.NEARING_MATURITY, S.MATURED): {SYSTEM},
    (S.NEARING_MATURITY, S.RENEWED): {INSTITUTION, ADMIN},
    (S.MATURED, S.RENEWED): {INSTITUTION, ADMIN},
    (S.ACTIVE, S.RELEASE_REQUESTED): {INSTITUTION, ADMIN},
    (S.NEARING_MATURITY, S.RELEASE_REQUESTED): {INSTITUTION, ADMIN},
    (S.MATURED, S.RELEASE_REQUESTED): {INSTITUTION, ADMIN},
    (S.RENEWED, S.RELEASED_CLOSED): {SYSTEM},
    (S.RELEASE_REQUESTED, S.RELEASED_CLOSED): {ADMIN},
    (S.RELEASE_REQUESTED, S.ACTIVE): {ADMIN},
    (S.RELEASE_REQUESTED, S.NEARING_MATURITY): {ADMIN},
    (S.RELEASE_REQUESTED, S.MATURED): {ADMIN},
}


def role_of(actor):
    return SYSTEM if actor is None else actor.role


def can_transition(from_status, to_status, role):
    return role in ALLOWED.get((from_status, to_status), set())


def change_status(fdr, to_status, actor, *, note="", request=None, audit=True):
    allowed_roles = ALLOWED.get((fdr.status, to_status))
    if allowed_roles is None:
        raise BusinessRuleError(f"A record cannot move from '{fdr.status}' to '{to_status}'.")
    if role_of(actor) not in allowed_roles:
        raise PermissionDenied("Your role cannot make this status change.")

    old = fdr.status
    fdr.status = to_status
    fdr.status_note = note[:2000]
    fdr.save(update_fields=["status", "status_note", "updated_at"])
    if audit:
        record_audit(
            action="fdr.status_changed", entity="FDR", entity_id=fdr.pk, actor=actor,
            old={"status": old}, new={"status": to_status, "note": note[:500]}, request=request,
        )
    return fdr
