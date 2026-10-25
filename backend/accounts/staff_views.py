from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAdminUser

from core.permissions import StrictModelPermissions

from .models import User
from .staff_serializers import (
    StaffMeSerializer,
    StaffUserDetailSerializer,
    StaffUserListSerializer,
)


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