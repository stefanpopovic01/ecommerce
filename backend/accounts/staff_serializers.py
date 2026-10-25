from rest_framework import serializers
from phonenumber_field.serializerfields import PhoneNumberField

from .models import User



class StaffMeSerializer(serializers.ModelSerializer):
    groups = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_superuser", "groups", "permissions"]
        read_only_fields = fields

    def get_permissions(self, obj):
        return sorted(obj.get_all_permissions())



class StaffUserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone",
                  "is_staff", "is_active", "email_verified_at", "created_at"]
        read_only_fields = fields



class StaffUserDetailSerializer(serializers.ModelSerializer):
    phone = PhoneNumberField(required=False, allow_blank=True)
    groups = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    has_password = serializers.SerializerMethodField()
    has_google = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone",
                  "is_staff", "is_active", "groups", "email_verified_at",
                  "has_password", "has_google", "last_login", "created_at", "updated_at"]
        read_only_fields = ["id", "email", "is_staff", "is_active", "groups",
                            "email_verified_at", "last_login", "created_at", "updated_at"]

    def get_has_password(self, obj):
        return obj.has_usable_password()

    def get_has_google(self, obj):
        return obj.oauth_accounts.exists()