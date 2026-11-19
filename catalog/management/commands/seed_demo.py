import json
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import Cinema, City, Movie, Screen, Seat, SeatCategory, Show
from catalog.services import create_show

LOCAL_TZ = ZoneInfo("Asia/Kolkata")

SEED_DATA_DIR = Path(__file__).resolve().parents[2] / "seed_data"

SEAT_ROWS: dict[str, str] = {
    **dict.fromkeys("ABC", SeatCategory.NORMAL),
    **dict.fromkeys("DEFG", SeatCategory.EXECUTIVE),
    **dict.fromkeys("HI", SeatCategory.PREMIUM),
    **dict.fromkeys("J", SeatCategory.RECLINER),
}
SEATS_PER_ROW = 12

SHOW_TIMES: tuple[time, ...] = (time(10, 0), time(14, 0), time(18, 0), time(21, 30))

SHOW_PRICES: dict[str, Decimal] = {
    SeatCategory.NORMAL: Decimal("150.00"),
    SeatCategory.EXECUTIVE: Decimal("200.00"),
    SeatCategory.PREMIUM: Decimal("250.00"),
    SeatCategory.RECLINER: Decimal("400.00"),
}

# Shows rotate through this many of the most recently released movies.
NOW_SHOWING_COUNT = 24

# Refreshed from movies.json when a movie already exists.
MOVIE_DETAIL_FIELDS: tuple[str, ...] = ("synopsis", "director", "cast", "genres")

# Required by the model. movies.json leaves these empty for real films whose
# values weren't certain; such entries are skipped rather than guessed.
REQUIRED_MOVIE_FIELDS: tuple[str, ...] = ("release_date", "duration_minutes", "certificate")


def _load_seed_file(name: str) -> Any:
    with (SEED_DATA_DIR / name).open(encoding="utf-8") as f:
        # Decimal keeps coordinates exact for the DecimalFields.
        return json.load(f, parse_float=Decimal)


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


def _seed_venues(counts: Counter) -> list[Screen]:
    """Create the cities, cinemas, screens and seats in cinemas.json.

    Returns every screen in file order, which fixes the show rotation.
    """
    screens: list[Screen] = []
    for city_data in _load_seed_file("cinemas.json")["cities"]:
        city, created = City.objects.get_or_create(
            slug=city_data["slug"],
            defaults={"name": city_data["name"], "state": city_data["state"]},
        )
        counts["cities"] += 1
        counts["cities_created"] += created

        for cinema_data in city_data["cinemas"]:
            cinema, created = Cinema.objects.get_or_create(
                city=city,
                name=cinema_data["name"],
                defaults={
                    "address": cinema_data["address"],
                    "latitude": cinema_data["latitude"],
                    "longitude": cinema_data["longitude"],
                },
            )
            counts["cinemas"] += 1
            counts["cinemas_created"] += created

            for screen_name in cinema_data["screens"]:
                screen, created = Screen.objects.get_or_create(cinema=cinema, name=screen_name)
                counts["screens"] += 1
                counts["screens_created"] += created
                counts["seats_created"] += _seed_seats(screen)
                screens.append(screen)

    return screens


def _seed_movies(counts: Counter, skipped: list[str]) -> list[Movie]:
    """Create or refresh the movies in movies.json; return the ones in the database."""
    movies: list[Movie] = []
    for data in _load_seed_file("movies.json"):
        missing = [field for field in REQUIRED_MOVIE_FIELDS if not data.get(field)]
        if missing:
            skipped.append(f"{data['title']} (no {', '.join(missing)})")
            continue

        details = {field: data[field] for field in MOVIE_DETAIL_FIELDS}
        movie, created = Movie.objects.get_or_create(
            title=data["title"],
            release_date=date.fromisoformat(data["release_date"]),
            defaults={
                "language": data["language"],
                "certificate": data["certificate"],
                "duration_minutes": data["duration_minutes"],
                **details,
            },
        )
        if created:
            counts["movies_created"] += 1
        else:
            changed = [field for field, value in details.items() if getattr(movie, field) != value]
            if changed:
                for field in changed:
                    setattr(movie, field, details[field])
                movie.save(update_fields=[*changed, "updated_at"])
                counts["movies_updated"] += 1
        movies.append(movie)

    return movies


def _seed_shows(counts: Counter, screens: list[Screen], movies: list[Movie]) -> None:
    """Create today's and tomorrow's shows that don't exist yet.

    A show is identified by (screen, starts_at). Each screen gets its own
    block of consecutive movies from the now-showing list, so screens in the
    same cinema never share a movie.
    """
    today = timezone.localdate(timezone=LOCAL_TZ)
    released = [movie for movie in movies if movie.release_date <= today]
    released.sort(key=lambda movie: (-movie.release_date.toordinal(), movie.title))
    now_showing = released[:NOW_SHOWING_COUNT]
    if not now_showing:
        return

    for day in (today, today + timedelta(days=1)):
        for screen_index, screen in enumerate(screens):
            for slot_index, slot in enumerate(SHOW_TIMES):
                starts_at = datetime.combine(day, slot, tzinfo=LOCAL_TZ)
                if Show.objects.filter(screen=screen, starts_at=starts_at).exists():
                    counts["shows_existing"] += 1
                    continue
                position = screen_index * len(SHOW_TIMES) + slot_index
                create_show(
                    movie=now_showing[position % len(now_showing)],
                    screen=screen,
                    starts_at=starts_at,
                    prices=SHOW_PRICES,
                )
                counts["shows_created"] += 1


class Command(BaseCommand):
    help = (
        "Seed demo data from catalog/seed_data: cities, cinemas, screens and seats "
        "from cinemas.json, movies from movies.json, and shows for today and "
        "tomorrow. Safe to run more than once."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        counts: Counter = Counter()
        skipped: list[str] = []

        with transaction.atomic():
            screens = _seed_venues(counts)
            movies = _seed_movies(counts, skipped)
            _seed_shows(counts, screens, movies)

        movies_unchanged = len(movies) - counts["movies_created"] - counts["movies_updated"]
        self.stdout.write(
            self.style.SUCCESS("Demo data ready.")
            + f"\n  Cities:  {counts['cities_created']} created, "
            f"{counts['cities'] - counts['cities_created']} existing"
            + f"\n  Cinemas: {counts['cinemas_created']} created, "
            f"{counts['cinemas'] - counts['cinemas_created']} existing"
            + f"\n  Screens: {counts['screens_created']} created, "
            f"{counts['screens'] - counts['screens_created']} existing"
            + f"\n  Seats:   {counts['seats_created']} created"
            + f"\n  Movies:  {counts['movies_created']} created, "
            f"{counts['movies_updated']} updated, {movies_unchanged} unchanged, "
            f"{len(skipped)} skipped (incomplete data)"
            + f"\n  Shows:   {counts['shows_created']} created, "
            f"{counts['shows_existing']} already existed"
        )
        if skipped:
            if options["verbosity"] >= 2:
                self.stdout.write("Skipped movies:\n  " + "\n  ".join(skipped))
            else:
                self.stdout.write("  (run with -v 2 to list skipped movies)")
