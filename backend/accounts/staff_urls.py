from django.urls import path
from rest_framework.routers import DefaultRouter

from .staff_views import StaffMeView, StaffUserViewSet

router = DefaultRouter()
router.register("users", StaffUserViewSet, basename="staff-user")

urlpatterns = [
    path("me/", StaffMeView.as_view(), name="staff_me"),
] + router.urls