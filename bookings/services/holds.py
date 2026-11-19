from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User
from bookings.models import ShowSeat, ShowSeatStatus
from catalog.constants import LATE_BOOKING_WINDOW
from catalog.models import Show
from core.error_codes import ErrorCode
from core.exceptions import ConflictError

MAX_SEATS_PER_HOLD = 10
HOLD_DURATION = timedelta(minutes=10)


def _seat_is_free(now: datetime) -> Q:
    return Q(status=ShowSeatStatus.AVAILABLE) | Q(
        status=ShowSeatStatus.HELD, held_until__lt=now
    )


def hold_seats(*, user: User, show: Show, seat_ids: list[int]) -> datetime:
    """Hold the given seats for this user for HOLD_DURATION.

    All seats are held, or none are. Raises ValidationError for bad input
    and ConflictError if the show can't be booked or a seat isn't free.
    """
    now = timezone.now()
    held_until = now + HOLD_DURATION

    if not seat_ids:
        raise ValidationError("Select at least one seat.")

    if len(set(seat_ids)) != len(seat_ids):
        raise ValidationError("The same seat was selected more than once.")

    if len(seat_ids) > MAX_SEATS_PER_HOLD:
        raise ValidationError(f"You can select up to {MAX_SEATS_PER_HOLD} seats.")

    if show.status != Show.Status.SCHEDULED:
        raise ConflictError("The show has been cancelled.")

    if show.starts_at + LATE_BOOKING_WINDOW < now:
        raise ConflictError("Booking for this show has closed.")

    with transaction.atomic():
        updated = ShowSeat.objects.filter(
            _seat_is_free(now=now), show=show, seat_id__in=seat_ids
        ).update(status=ShowSeatStatus.HELD, held_by=user, held_until=held_until)

        if updated != len(seat_ids):
            raise ConflictError(
                "Some of the selected seats are no longer available.",
                code=ErrorCode.SEATS_UNAVAILABLE,
            )

    return held_until
