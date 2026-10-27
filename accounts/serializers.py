from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from institutions.models import Institution

from .models import User


class UserSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    institution_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "name", "role", "institution_id", "status", "last_login"]
        read_only_fields = fields


class UserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=User.Role.choices)
    institution = serializers.PrimaryKeyRelatedField(
        queryset=Institution.objects.all(), required=False, allow_null=True
    )

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        if attrs["role"] == User.Role.INSTITUTION_USER:
            if attrs.get("institution") is None:
                raise serializers.ValidationError({"institution": "Institution users must belong to an institution."})
        else:
            attrs["institution"] = None  # staff roles are not tied to an institution
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value, user=self.context["request"].user)
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
