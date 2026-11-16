from rest_framework import generics
from rest_framework.permissions import AllowAny

from accounts.serializers import RegisterSerializer

class RegisterView(generics.CreateAPIView):
    serializer = RegisterSerializer
    permission_classes = [AllowAny]