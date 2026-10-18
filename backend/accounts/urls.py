from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView

from .views import RegisterView, MyTokenObtainPairView, MeView, GoogleLoginView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'), # POST
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'), # POST
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'), # POST
    path('logout/', TokenBlacklistView.as_view(), name='logout'), # The frontend sends {"refresh": "<token>"}
    path('google/', GoogleLoginView.as_view(), name='google_login'), # POST {"credential": "..."}
    path('me/', MeView.as_view(), name='me')
]

