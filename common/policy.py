"""Server-side authorization: the role-to-action matrix from the design document (Section 3).

Every view calls `require()` before doing any work. The interface hiding
buttons is convenience only; this module is the real control.
"""
from rest_framework.exceptions import PermissionDenied

INSTITUTION = "institution_user"
OFFICER = "scrutiny_officer"
ADMIN = "administrator"
AUDITOR = "auditor"

MATRIX = {
    INSTITUTION: {
        "view_fdrs", "register_fdr", "import_fdrs", "upload_documents", "reply_query",
        "submit_request", "view_reports", "view_dashboard",
    },
    OFFICER: {
        "view_fdrs", "review_fdr", "raise_query", "record_bank_confirmation", "recommend_release",
        "view_reports", "view_dashboard", "view_limited_audit_logs", "view_institutions",
    },
    ADMIN: {
        "view_fdrs", "register_fdr", "import_fdrs", "upload_documents", "review_fdr", "raise_query",
        "record_bank_confirmation", "submit_request", "recommend_release", "approve_release",
        "manage_institutions", "view_institutions", "manage_users", "change_settings",
        "view_reports", "view_dashboard", "view_audit_logs", "view_reminders",
    },
    AUDITOR: {"view_fdrs", "view_reports", "view_dashboard", "view_audit_logs", "view_reminders"},
}


def can(user, action):
    return bool(user and user.is_authenticated and action in MATRIX.get(user.role, set()))


def require(user, action):
    if not can(user, action):
        raise PermissionDenied("Your role is not allowed to perform this action.")


def scope_fdrs(user, queryset):
    """Institution users only ever see their own institution's records."""
    if user.role == INSTITUTION:
        if not user.institution_id:
            return queryset.none()
        return queryset.filter(institution_id=user.institution_id)
    return queryset


def is_own_institution(user, institution_id):
    return user.role != INSTITUTION or user.institution_id == institution_id


def can_approve_release(user, request_obj):
    """Separation of duties: the approver must be an administrator who neither
    submitted nor recommended the request."""
    return (
        user.role == ADMIN
        and user.pk != request_obj.submitted_by_id
        and user.pk != request_obj.recommended_by_id
    )
