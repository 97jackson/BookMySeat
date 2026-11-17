from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from typing import ClassVar


from core.models import BaseModel


phone_validator = RegexValidator(
    regex=r"^\+[1-9]\d{7,14}$",
    message="Enter the phone number in international format, e.g. +919876543210.",
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        return self.get(email__iexact=username)

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        if not password:
            raise ValueError("Superuser must have a password.")
        extra_fields["role"] = self.model.UserRole.SUPER_ADMIN
        extra_fields["email_verified_at"] = timezone.now()
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, BaseModel):
    class UserRole(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        ADMIN = "admin", "Admin"
        STAFF = "staff", "Staff"
        CUSTOMER = "customer", "Customer"

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(
        max_length=16, unique=True, null=True, blank=True, validators=[phone_validator]
    )
    role = models.CharField(
        max_length=20, choices=UserRole.choices, default=UserRole.CUSTOMER
    )
    is_active = models.BooleanField(default=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)

    objects: ClassVar[UserManager] = UserManager() # pyright: ignore[reportIncompatibleVariableOverride]

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name"]

    def __str__(self) -> str:
        return self.email
