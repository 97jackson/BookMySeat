from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction

from bookings.services import create_show_seats
from catalog.models import Movie, Screen, Show, ShowPrice

CLEANING_BUFFER = timedelta(minutes=15)


def create_show(
    *,
    movie: Movie,
    screen: Screen,
    starts_at: datetime,
    prices: dict[str, Decimal],
) -> Show:
    """Create a show with its per-category prices and its seat inventory.

    `prices` keys are SeatCategory values. Everything is created in one
    transaction, so a failure leaves no partial show behind.
    """
    ends_at = starts_at + timedelta(minutes=movie.duration_minutes) + CLEANING_BUFFER

    with transaction.atomic():
        show = Show.objects.create(
            movie=movie,
            screen=screen,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        ShowPrice.objects.bulk_create(
            ShowPrice(show=show, category=category, price=price)
            for category, price in prices.items()
        )
        create_show_seats(show)

    return show
