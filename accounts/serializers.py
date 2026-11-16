from django.contrib.auth import password_validation
from rest_framework import serializers

from accounts import services
from accounts.models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = [
            "public_id",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "password",
        ]
        read_only_fields = ["public_id"]
        extra_kwargs = {"phone_number": {"allow_blank": False}}

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value: str) -> str:
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        return services.register_user(**validated_data)