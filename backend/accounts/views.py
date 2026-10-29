import logging
logger = logging.getLogger(__name__)

from django.db import transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import User, Address
from .services import get_or_create_google_user, send_verification_email, send_password_reset_email, reset_password, change_password, delete_account, send_account_deletion_email
from .serializers import UserSerializer, RegisterSerializer, MyTokenObtainPairSerializer, DeleteAccountSerializer, GoogleLoginSerializer, VerifyEmailSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer, ChangePasswordSerializer
from .serializers import AccountDeletionConfirmSerializer, AddressSerializer



class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle] 
    throttle_scope = "register"

    def perform_create(self, serializer):
        user = serializer.save()
        transaction.on_commit(lambda: send_verification_email(user)) # With on_commit, the email only goes out once the user is permanently saved.



class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle] 
    throttle_scope = "login"



class MeView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "delete"]

    def get_object(self):
        return self.request.user

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()

        if not user.has_usable_password():
            return Response(
                {"detail": "Your account uses Google sign-in. Request a deletion link instead."},
                status=status.HTTP_400_BAD_REQUEST,
        )

        if user.is_staff:
            return Response(
                {"detail": "Staff accounts are managed by an administrator."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = DeleteAccountSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        delete_account(user)
        return Response(status=status.HTTP_204_NO_CONTENT)

# Context as a dictionary where you can put extra information that a serializer needs but that isn't part of the data sent by the client.
# data=request.data --- {"password": "myPassword123"} | context={"request": request} --- {"request": <HTTP request object>}



class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = get_or_create_google_user(serializer.validated_data["credential"])
        if not user.is_active:
            return Response({"detail": "Account is disabled."}, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": UserSerializer(user, context={"request": request}).data
        })



class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        if user.email_verified_at is None:
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at", "updated_at"])
        return Response({"detail": "Email verified."})



class ResendVerificationEmailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle] 
    throttle_scope = "email_verification"

    def post(self, request):
        if request.user.email_verified_at is not None:
            return Response({"detail": "Email already verified."}, status=status.HTTP_400_BAD_REQUEST)

        send_verification_email(request.user)
        return Response({"detail": "Verification email sent."})



class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(
            email__iexact=serializer.validated_data["email"], is_active=True
        ).first()

        if user:
            try:
                send_password_reset_email(user)
            except Exception:
                logger.exception("Password reset email failed for user %s", user.pk)

        return Response(
            {"detail": "If an account with this email exists, a reset link was sent."}
        )



class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reset_password(serializer.validated_data["user"], serializer.validated_data["password"])
        return Response({"detail": "Password has been reset."})



class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_change"

    def post(self, request):
        if not request.user.has_usable_password():
            return Response(
                {"detail": "Your account uses Google sign-in. Use password reset to set a password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        tokens = change_password(request.user, serializer.validated_data["new_password"])

        return Response(tokens)



class AccountDeletionRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "account_deletion"

    def post(self, request):
        if request.user.has_usable_password():
            return Response(
                {"detail": "Confirm deletion with your password instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        send_account_deletion_email(request.user)
        return Response({"detail": "A confirmation link was sent to your email."})


class AccountDeletionConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AccountDeletionConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        delete_account(serializer.validated_data["user"])
        return Response(status=status.HTTP_204_NO_CONTENT)



class AddressViewSet(ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user).order_by(
            "-is_default_shipping", "-is_default_billing", "-created_at"
        )

    @transaction.atomic
    def perform_create(self, serializer):
        has_addresses = Address.objects.filter(user=self.request.user).exists()

        is_default_shipping = serializer.validated_data.get("is_default_shipping")
        is_default_billing = serializer.validated_data.get("is_default_billing")


        if not has_addresses:
            serializer.save(
                user=self.request.user,
                is_default_shipping=True,
                is_default_billing=True,
            )
        else:
            if is_default_billing is True:
                Address.objects.filter(user=self.request.user, is_default_billing=True).update(is_default_billing=False)
            if is_default_shipping is True:
                Address.objects.filter(user=self.request.user, is_default_shipping=True).update(is_default_shipping=False)
            serializer.save(user=self.request.user)

    @transaction.atomic
    def perform_update(self, serializer):

        is_default_shipping = serializer.validated_data.get("is_default_shipping")
        is_default_billing = serializer.validated_data.get("is_default_billing")

        if is_default_billing is True:
            Address.objects.filter(
                user=self.request.user,
                is_default_billing=True,
            ).exclude(pk=serializer.instance.pk).update(
                is_default_billing=False
            )

        if is_default_shipping is True:
            Address.objects.filter(
                user=self.request.user,
                is_default_shipping=True,
            ).exclude(pk=serializer.instance.pk).update(
                is_default_shipping=False
            )

        serializer.save()

