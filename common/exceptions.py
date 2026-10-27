"""One consistent JSON error format for every API error.

Shape: {"error": {"code": "...", "message": "...", "fields": {...}}}
`fields` is present only for validation errors and lists each field's problems.
Internal details are logged, never returned to the user.
"""
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class BusinessRuleError(APIException):
    """The request is well-formed but the workflow does not allow it right now."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "business_rule"
    default_detail = "This action is not allowed in the current state."


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "This record conflicts with an existing one."


class AccountLockedError(APIException):
    status_code = 423
    default_code = "account_locked"
    default_detail = "This account is temporarily locked after repeated failed sign-ins. Try again later."


class FeatureUnavailableError(APIException):
    status_code = status.HTTP_501_NOT_IMPLEMENTED
    default_code = "not_implemented"
    default_detail = "This feature is not available in this release."


def exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.messages)

    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled server error", exc_info=exc)
        return Response(
            {"error": {"code": "server_error", "message": "An unexpected error occurred. Please try again."}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, ValidationError):
        error = {
            "code": "validation_error",
            "message": "Please correct the highlighted fields.",
            "fields": response.data,
        }
    else:
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        error = {
            "code": getattr(exc, "default_code", "error"),
            "message": str(detail or "The request could not be completed."),
        }
    response.data = {"error": error}
    return response
