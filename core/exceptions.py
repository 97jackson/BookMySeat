from collections.abc import Iterator
from typing import Any, TypedDict

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler

from core.camel_case import to_camel
from core.error_codes import ErrorCode

_REQUIRED_CODES = frozenset({"required", "blank", "null"})
_FIELDS_MESSAGE = "Please correct the highlighted fields."
_INVALID_INPUT_MESSAGE = "Invalid input."
_REQUEST_FAILED_MESSAGE = "Request failed."


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state."
    default_code = ErrorCode.CONFLICT


class ErrorItem(TypedDict):
    field: str | None
    message: str


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, ValidationError):
        code: str = ErrorCode.VALIDATION_ERROR
        details = list(_flatten_errors(exc.detail))
        message = _validation_message(details)
    else:
        code = _error_code(exc, response.data)
        details = []
        message = _detail_message(response.data)

    response.data = {
        "has_error": True,
        "status": response.status_code,
        "code": str(code),
        "message": message,
        "details": details,
        "response": None,
    }
    return response


def _flatten_errors(data: Any, path: tuple[str, ...] = ()) -> Iterator[ErrorItem]:
    if isinstance(data, dict):
        for key, value in data.items():
            if key == api_settings.NON_FIELD_ERRORS_KEY:
                yield from _flatten_errors(value, path)
            else:
                yield from _flatten_errors(value, (*path, str(key)))
    elif isinstance(data, list):
        for index, item in enumerate(data):
            # Nested many=True serializers return one dict per item; index them so
            # the client knows which item failed. Plain message lists stay unindexed.
            item_path = (*path, str(index)) if isinstance(item, dict) else path
            yield from _flatten_errors(item, item_path)
    else:
        yield _error_item(data, path)


def _error_item(error: Any, path: tuple[str, ...]) -> ErrorItem:
    if not path:
        return {"field": None, "message": str(error)}

    message = str(error)
    if getattr(error, "code", None) in _REQUIRED_CODES:
        message = f"{_label(path)} is required."
    return {"field": ".".join(to_camel(part) for part in path), "message": message}


def _label(path: tuple[str, ...]) -> str:
    # Skip list indexes so "tags.1" is labelled "Tags", not "1".
    field_name = next((part for part in reversed(path) if not part.isdigit()), path[-1])
    label = field_name.replace("_", " ")
    return label[:1].upper() + label[1:]


def _validation_message(details: list[ErrorItem]) -> str:
    if not details:
        return _INVALID_INPUT_MESSAGE
    return next(
        (item["message"] for item in details if item["field"] is None),
        _FIELDS_MESSAGE,
    )


def _error_code(exc: Exception, data: Any) -> str:
    if isinstance(exc, APIException):
        codes = exc.get_codes()
        if isinstance(codes, str):
            return codes
    if isinstance(data, dict) and "code" in data:
        return str(data["code"])
    if isinstance(exc, Http404):
        return ErrorCode.NOT_FOUND
    if isinstance(exc, DjangoPermissionDenied):
        return ErrorCode.PERMISSION_DENIED
    return ErrorCode.ERROR


def _detail_message(data: Any) -> str:
    if isinstance(data, dict) and "detail" in data:
        return str(data["detail"])
    return _REQUEST_FAILED_MESSAGE
