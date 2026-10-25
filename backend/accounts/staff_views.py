from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction

from rest_framework import generics, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAdminUser

from core.permissions import StrictModelPermissions

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import require_perm

from .models import User
from .staff_serializers import (
    StaffMeSerializer,
    StaffUserDetailSerializer,
    StaffUserListSerializer,
    InviteStaffSerializer
)

from .services import invite_staff, blacklist_all_tokens, send_password_reset_email, send_verification_email

class StaffMeView(generics.RetrieveAPIView):
    serializer_class = StaffMeSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        return self.request.user



class StaffUserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser, StrictModelPermissions]
    http_method_names = ["get", "patch", "post"]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_staff", "is_active"]
    search_fields = ["email", "first_name", "last_name", "phone"]
    ordering_fields = ["created_at", "email", "last_login"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = User.objects.prefetch_related("groups")
        if not self.request.user.is_superuser:
            qs = qs.filter(is_superuser=False)
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return StaffUserListSerializer
        return StaffUserDetailSerializer

    def create(self, request, *args, **kwargs):
        # users are never created through a plain POST here; only via the invite action
        return self.http_method_not_allowed(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="invite-staff")
    def invite_staff(self, request):
        serializer = InviteStaffSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = invite_staff(**serializer.validated_data)
        return Response(StaffUserDetailSerializer(user).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="set-groups",
            permission_classes=[IsAdminUser, require_perm("accounts.change_user")])
    def set_groups(self, request, pk=None):
        user = self.get_object()

        if user == request.user:
            return Response({"detail": "You cannot change your own groups."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not user.is_staff:
            return Response({"detail": "User is not a staff member."},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = SetGroupsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_staff_groups(user, serializer.validated_data["groups"])
        return Response(StaffUserDetailSerializer(user).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser, require_perm("accounts.change_user")])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        if user == request.user:
            return Response({"detail": "You cannot deactivate your own account."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user.is_active = False
            user.save(update_fields=["is_active", "updated_at"])
            blacklist_all_tokens(user)
        
        return Response(StaffUserDetailSerializer(user).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser, require_perm("accounts.change_user")])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active", "updated_at"])

        return Response(StaffUserDetailSerializer(user).data)

    @action(detail=True, methods=["post"], url_path="send-password-reset", permission_classes=[IsAdminUser, require_perm("accounts.change_user")])
    def send_password_reset(self, request, pk=None):
        user = self.get_object()
        if not user.is_active:
            return Response({"detail": "User is deactivated."}, status=status.HTTP_400_BAD_REQUEST)

        send_password_reset_email(user)

        return Response({"detail": "Password reset email sent."})

    @action(detail=True, methods=["post"], url_path="resend-verification", permission_classes=[IsAdminUser, require_perm("accounts.change_user")])
    def resend_verification(self, request, pk=None):
        user = self.get_object()
        if user.email_verified_at is not None:
            return Response({"detail": "Email already verified."}, status=status.HTTP_400_BAD_REQUEST)
        send_verification_email(user)
        return Response({"detail": "Verification email sent."})