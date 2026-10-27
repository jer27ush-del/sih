from django.conf import settings
from django.core.mail import send_mail

from accounts.models import User
from common.policy import ADMIN, INSTITUTION, OFFICER

from .models import Notification


def institution_users(institution_id):
    return list(User.objects.filter(institution_id=institution_id, role=INSTITUTION, is_active=True))


def officers():
    return list(User.objects.filter(role=OFFICER, is_active=True))


def administrators():
    return list(User.objects.filter(role=ADMIN, is_active=True))


def notify(users, *, type, message, link=""):
    """Create in-portal notifications and send a plain email to each recipient.
    Email failures are logged by Django and never block the workflow."""
    unique_users = {user.pk: user for user in users}.values()
    for user in unique_users:
        Notification.objects.create(user=user, type=type, message=message[:500], link=link[:255])
        send_mail(
            subject="AICTE FDR Portal notification",
            message=f"{message}\n\nOpen the portal to view it: {settings.FRONTEND_URL}{link}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
