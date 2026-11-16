from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler

from core.camel_case import to_camel


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    response.data = {
        "has_error": True,
        "message": _build_message(response.data),
        "response": None,
    }
    return response


def _build_message(data) -> str:
    if isinstance(data, dict) and "detail" in data:
        return str(data["detail"])

    messages = [
        f"{field}: {error}" if field else error
        for field, error in _flatten_errors(data)
    ]
    return " ".join(messages) or "Something went wrong."


def _flatten_errors(data, prefix: str = ""):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == api_settings.NON_FIELD_ERRORS_KEY:
                name = prefix
            else:
                field = to_camel(str(key))
                name = f"{prefix}.{field}" if prefix else field
            yield from _flatten_errors(value, name)
    elif isinstance(data, list):
        for item in data:
            yield from _flatten_errors(item, prefix)
    else:
        yield prefix, str(data)