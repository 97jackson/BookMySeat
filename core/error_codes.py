from enum import StrEnum


class ErrorCode(StrEnum):
    # Generic
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    NOT_AUTHENTICATED = "not_authenticated"
    AUTHENTICATION_FAILED = "authentication_failed"
    CONFLICT = "conflict"
    THROTTLED = "throttled"
    ERROR = "error"

    # Booking
    SOLD_OUT = "sold_out"
    HOLD_EXPIRED = "hold_expired"
    SEATS_UNAVAILABLE = "seats_unavailable"
