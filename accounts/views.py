from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import generics
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import record_audit
from common.exceptions import AccountLockedError, BusinessRuleError
from common.policy import require

from .models import User
from .serializers import (
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    UserCreateSerializer,
    UserSerializer,
)


def send_password_link(user):
    """Email a single-use, time-limited link to set or reset a password."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    send_mail(
        subject="AICTE FDR Portal: set your password",
        message=(
            f"Hello {user.name},\n\nUse this link to set your password. It expires in one hour:\n{link}\n\n"
            "If you did not expect this email, you can ignore it."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


class CsrfView(APIView):
    """Call once before the first POST; the response also sets the CSRF cookie."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrf_token": get_token(request)})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        password = str(request.data.get("password", ""))
        now = timezone.now()
        user = User.objects.filter(email=email).first()

        if user and user.locked_until and user.locked_until > now:
            raise AccountLockedError()

        if user is None or not user.is_active or not user.check_password(password):
            if user is not None and user.is_active:
                user.failed_login_count += 1
                if user.failed_login_count >= settings.LOGIN_LOCK_THRESHOLD:
                    user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
                    user.failed_login_count = 0
                user.save(update_fields=["failed_login_count", "locked_until"])
            record_audit(
                action="auth.login_failed", entity="User", entity_id=str(user.pk) if user else "unknown",
                new={"email": email}, request=request,
            )
            raise AuthenticationFailed("Invalid email or password.")

        user.failed_login_count = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_count", "locked_until"])
        login(request, user)
        record_audit(action="auth.login", entity="User", entity_id=user.pk, actor=user, request=request)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    def post(self, request):
        record_audit(action="auth.logout", entity="User", entity_id=request.user.pk, actor=request.user, request=request)
        logout(request)
        return Response(status=204)


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class PasswordChangeView(APIView):
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            raise ValidationError({"current_password": ["Current password is incorrect."]})
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)
        record_audit(action="auth.password_changed", entity="User", entity_id=user.pk, actor=user, request=request)
        return Response(status=204)


class PasswordResetRequestView(APIView):
    """Always answers the same way, so it cannot be used to discover which emails have accounts."""

    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user:
            send_password_link(user)
        return Response({"detail": "If an account exists for that email, a reset link has been sent."}, status=202)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(data["uid"])))
        except (TypeError, ValueError, OverflowError, User.DoesNotExist, DjangoValidationError):
            user = None
        if user is None or not default_token_generator.check_token(user, data["token"]):
            raise ValidationError({"token": ["This reset link is invalid or has expired."]})
        try:
            validate_password(data["new_password"], user=user)
        except DjangoValidationError as exc:
            raise ValidationError({"new_password": list(exc.messages)})
        user.set_password(data["new_password"])
        user.failed_login_count = 0
        user.locked_until = None
        user.save()  # changing the password also invalidates the reset token (single use)
        record_audit(action="auth.password_reset", entity="User", entity_id=user.pk, actor=user, request=request)
        return Response(status=204)


class UserListCreateView(generics.ListCreateAPIView):
    """Administrators create institution and staff accounts. New users get a set-password link."""

    serializer_class = UserSerializer

    def get_queryset(self):
        require(self.request.user, "manage_users")
        return User.objects.select_related("institution").order_by("name")

    def create(self, request, *args, **kwargs):
        require(request.user, "manage_users")
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.create_user(
            email=data["email"], name=data["name"], role=data["role"], institution=data.get("institution")
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        send_password_link(user)
        record_audit(
            actor=request.user, action="user.created", entity="User", entity_id=user.pk,
            new=UserSerializer(user).data, request=request,
        )
        return Response(UserSerializer(user).data, status=201)


class UserDetailView(APIView):
    """Deactivate or reactivate a user. Accounts are never deleted, so history stays intact."""

    def patch(self, request, pk):
        require(request.user, "manage_users")
        user = get_object_or_404(User, pk=pk)
        new_status = request.data.get("status")
        if new_status not in (None, "Active", "Inactive"):
            raise ValidationError({"status": ["Use 'Active' or 'Inactive'."]})
        old = UserSerializer(user).data
        if new_status == "Inactive":
            if user.pk == request.user.pk:
                raise BusinessRuleError("You cannot deactivate your own account.")
            user.is_active = False
        elif new_status == "Active":
            user.is_active = True
        user.save(update_fields=["is_active"])
        record_audit(
            actor=request.user, action="user.updated", entity="User", entity_id=user.pk,
            old=old, new=UserSerializer(user).data, request=request,
        )
        return Response(UserSerializer(user).data)
