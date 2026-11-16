# accounts/backends.py
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailOrPhoneBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get(User.USERNAME_FIELD)
        if not identifier or password is None:
            return None

        identifier = identifier.strip()
        if "@" in identifier:
            lookup = {"email__iexact": identifier}
        else:
            lookup = {"phone_number": identifier}

        try:
            user = User.objects.get(**lookup)
        except User.DoesNotExist:
            User().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None