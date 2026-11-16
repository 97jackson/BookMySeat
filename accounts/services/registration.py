from accounts.models import User


def register_user(email: str, password: str, **fields) -> User:
    return User.objects.create(email=email, password=password, **fields)