from rest_framework import serializers
from .models import User
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password as django_validate_password
from phonenumber_field.serializerfields import PhoneNumberField

from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator

from .tokens import email_verification_token

class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    phone = PhoneNumberField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password', 'phone']

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        django_validate_password(value)
        return value

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user
    

class UserSerializer(serializers.ModelSerializer):
    phone = PhoneNumberField(required=False, allow_blank=True)
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'phone', 'role', 'email_verified_at', 'created_at', 'updated_at']
        read_only_fields = ["id", "email", "role", "email_verified_at", "created_at", "updated_at"]


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user, context={'request': self.context.get('request')}).data
        return data
    

class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Incorrect password.")
        return value


class GoogleLoginSerializer(serializers.Serializer):
    credential = serializers.CharField()

    def validate_credential(self, value):
        try:
            payload = id_token.verify_oauth2_token(
                value, google_requests.Request(), settings.GOOGLE_CLIENT_ID
            )
        except ValueError:
            raise serializers.ValidationError("Invalid Google token.")

        if not payload.get("email_verified"):
            raise serializers.ValidationError("Google email is not verified.")

        return payload


class VerifyEmailSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()

    def validate(self, attrs):
        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist, DjangoValidationError):
            raise serializers.ValidationError("Invalid verification link.")

        # Already verified: treat as success (user clicked the link twice)
        if user.email_verified_at is not None:
            return {"user": user}

        if not email_verification_token.check_token(user, attrs["token"]):
            raise serializers.ValidationError("Invalid or expired verification link.")

        return {"user": user}


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist, DjangoValidationError):
            raise serializers.ValidationError("Invalid or expired reset link.")

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError("Invalid or expired reset link.")

        django_validate_password(attrs["password"], user=user) # Passing user=user to the password validator lets UserAttributeSimilarityValidator reject passwords too similar to the user’s own name or email
        attrs["user"] = user 
        return attrs

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context["request"].user 
        if not user.check_password(value):
            raise serializers.ValidationError("Incorrect password.")
        return value

    def validate(self, attrs):
        user = self.context["request"].user 
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": ["New password must be different from the current password."]})

        try:
            django_validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"new_password": list(e.messages)})

        return attrs

    
# TODO (OAuth): users without a usable password need email-code confirmation instead
