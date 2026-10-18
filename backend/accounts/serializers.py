from rest_framework import serializers
from .models import User
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password as django_validate_password
from phonenumber_field.serializerfields import PhoneNumberField

from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

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

# payload = {
#     "iss": "https://accounts.google.com",
#     "sub": "109876543210987654321",
#     "email": "user@example.com",
#     "email_verified": True,
#     "name": "Alex Example",
#     "picture": "https://example.com/profile.jpg",
#     "aud": "your-google-client-id",
#     "exp": 1790000000,
# }

# TODO (OAuth): users without a usable password need email-code confirmation instead
