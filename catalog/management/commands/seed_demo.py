from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import Cinema, City, Movie, Screen, Seat, SeatCategory, Show
from catalog.services import create_show

LOCAL_TZ = ZoneInfo("Asia/Kolkata")

SCREEN_NAMES: tuple[str, ...] = ("Screen 1", "Screen 2")

SEAT_ROWS: dict[str, str] = {
    **dict.fromkeys("ABC", SeatCategory.NORMAL),
    **dict.fromkeys("DEFG", SeatCategory.EXECUTIVE),
    **dict.fromkeys("HI", SeatCategory.PREMIUM),
    **dict.fromkeys("J", SeatCategory.RECLINER),
}
SEATS_PER_ROW = 12

DEMO_MOVIES: tuple[dict[str, Any], ...] = (
    {
        "title": "Vazhiyorathe Velicham",
        "language": "Malayalam",
        "description": "A night-bus conductor and a runaway teenager cross Kerala in one long night.",
        "duration_minutes": 150,
        "certificate": Movie.Certificate.UA,
        "release_date": date(2026, 11, 6),
    },
    {
        "title": "The Midnight Signal",
        "language": "English",
        "description": "A radio astronomer picks up a message that seems to come from her own future.",
        "duration_minutes": 125,
        "certificate": Movie.Certificate.UA,
        "release_date": date(2026, 10, 30),
    },
)

SHOW_TIMES: tuple[time, ...] = (time(10, 0), time(14, 0), time(18, 0), time(21, 30))

SHOW_PRICES: dict[str, Decimal] = {
    SeatCategory.NORMAL: Decimal("150.00"),
    SeatCategory.EXECUTIVE: Decimal("200.00"),
    SeatCategory.PREMIUM: Decimal("250.00"),
    SeatCategory.RECLINER: Decimal("400.00"),
}


def _seed_seats(screen: Screen) -> int:
    """Create any missing seats for the screen; return how many were created."""
    existing = set(Seat.objects.filter(screen=screen).values_list("row", "number"))
    missing = [
        Seat(screen=screen, row=row, number=number, category=category)
        for row, category in SEAT_ROWS.items()
        for number in range(1, SEATS_PER_ROW + 1)
        if (row, number) not in existing
    ]
    return len(Seat.objects.bulk_create(missing))


def _seed_shows(screens: list[Screen], movies: list[Movie]) -> tuple[int, int]:
    """Create today's and tomorrow's shows that don't exist yet.

    A show is identified by (screen, starts_at). Movies alternate slot by
    slot, and each screen starts on a different movie.
    Returns (created, skipped).
    """
    today = timezone.localdate(timezone=LOCAL_TZ)
    created = 0
    skipped = 0

    for day in (today, today + timedelta(days=1)):
        for screen_index, screen in enumerate(screens):
            for slot_index, slot in enumerate(SHOW_TIMES):
                starts_at = datetime.combine(day, slot, tzinfo=LOCAL_TZ)
                if Show.objects.filter(screen=screen, starts_at=starts_at).exists():
                    skipped += 1
                    continue
                movie = movies[(screen_index + slot_index) % len(movies)]
                create_show(
                    movie=movie,
                    screen=screen,
                    starts_at=starts_at,
                    prices=SHOW_PRICES,
                )
                created += 1

    return created, skipped


class Command(BaseCommand):
    help = (
        "Seed demo data: a cinema in Trivandrum with two screens, seats, two movies "
        "and shows for today and tomorrow. Safe to run more than once."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        with transaction.atomic():
            city, city_created = City.objects.get_or_create(
                slug="trivandrum-kerala",
                defaults={"name": "Trivandrum", "state": "Kerala"},
            )
            cinema, cinema_created = Cinema.objects.get_or_create(
                city=city,
                name="Demo Cinemas",
                defaults={
                    "address": "MG Road, Thiruvananthapuram, Kerala 695001",
                    "latitude": Decimal("8.498700"),
                    "longitude": Decimal("76.949600"),
                },
            )

            screens: list[Screen] = []
            screens_created = 0
            seats_created = 0
            for name in SCREEN_NAMES:
                screen, created = Screen.objects.get_or_create(cinema=cinema, name=name)
                screens.append(screen)
                screens_created += created
                seats_created += _seed_seats(screen)

            movies: list[Movie] = []
            movies_created = 0
            for movie_fields in DEMO_MOVIES:
                movie, created = Movie.objects.get_or_create(
                    title=movie_fields["title"],
                    language=movie_fields["language"],
                    defaults=movie_fields,
                )
                movies.append(movie)
                movies_created += created

            shows_created, shows_skipped = _seed_shows(screens, movies)

        self.stdout.write(
            self.style.SUCCESS("Demo data ready.")
            + f"\n  City:    {city} ({'created' if city_created else 'existing'})"
            + f"\n  Cinema:  {cinema} ({'created' if cinema_created else 'existing'})"
            + f"\n  Screens: {screens_created} created, {len(screens) - screens_created} existing"
            + f"\n  Seats:   {seats_created} created"
            + f"\n  Movies:  {movies_created} created, {len(movies) - movies_created} existing"
            + f"\n  Shows:   {shows_created} created, {shows_skipped} already existed"
        )
