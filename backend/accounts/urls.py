from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView

from .views import RegisterView, MyTokenObtainPairView, MeView, GoogleLoginView, VerifyEmailView, ResendVerificationEmailView, PasswordResetRequestView, PasswordResetConfirmView, ChangePasswordView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'), # POST
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'), # POST
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'), # POST
    path('logout/', TokenBlacklistView.as_view(), name='logout'), # The frontend sends {"refresh": "<token>"}
    path('google/', GoogleLoginView.as_view(), name='google_login'), # POST {"credential": "..."}
    path('verify-email/', VerifyEmailView.as_view(), name='verify_email'), # POST {"uid": "...", "token": "..."}
    path('verify-email/resend/', ResendVerificationEmailView.as_view(), name='verify_email_resend'), # POST, authenticated
    path("password-reset/", PasswordResetRequestView.as_view(), name="password_reset"),                 # POST {"email": "..."}
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),  # POST {"uid", "token", "password"}
    path("password-change/", ChangePasswordView.as_view(), name="password_change"),  # POST {"old_password", "new_password"}, authenticated
    path('me/', MeView.as_view(), name='me')
]
