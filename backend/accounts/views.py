from django.db import transaction
from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import User
from .services import get_or_create_google_user
from .serializers import UserSerializer, RegisterSerializer, MyTokenObtainPairSerializer, DeleteAccountSerializer, GoogleLoginSerializer

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class MeView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "delete"]

    def get_object(self):
        return self.request.user

    def destroy(self, request, *args, **kwargs):
        serializer = DeleteAccountSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True) # If the password is correct code continues if not raises a ValidationError

        user = self.get_object()
        with transaction.atomic(): # Django's way of grouping db operations into a single atomic transaction.
            for token in OutstandingToken.objects.filter(user=user): # Find every token associated with user, blacklist it, when done delete user.
                BlacklistedToken.objects.get_or_create(token=token)
            user.delete()

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