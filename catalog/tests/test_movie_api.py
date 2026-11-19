from datetime import date, datetime, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.constants import LATE_BOOKING_WINDOW
from catalog.models import Cinema, City, Movie, Screen, SeatCategory, Show
from catalog.services import create_show
from core.error_codes import ErrorCode

URL = "/api/movies/"
PRICES = {SeatCategory.NORMAL: Decimal("200.00")}


def _make_screen(city: City) -> Screen:
    cinema = Cinema.objects.create(
        city=city, name=f"{city.name} Cinema", address="1 Main St"
    )
    return Screen.objects.create(cinema=cinema, name="Screen 1")


def _make_movie(title: str, release_date: date) -> Movie:
    return Movie.objects.create(
        title=title,
        duration_minutes=120,
        language="Malayalam",
        certificate=Movie.Certificate.UA,
        release_date=release_date,
    )


def _add_show(movie: Movie, screen: Screen, starts_at: datetime) -> Show:
    return create_show(movie=movie, screen=screen, starts_at=starts_at, prices=PRICES)


class MovieListAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        kochi = City.objects.create(name="Kochi", state="Kerala", slug="kochi")
        chennai = City.objects.create(name="Chennai", state="Tamil Nadu", slug="chennai")
        cls.kochi_screen = _make_screen(kochi)
        chennai_screen = _make_screen(chennai)

        # Listed in Kochi. Creation order and release dates are chosen so the
        # expected order differs from id order and from plain title order.
        cls.upcoming = _make_movie("Upcoming", date(2026, 2, 1))
        _add_show(cls.upcoming, cls.kochi_screen, now + timedelta(days=1))

        # Not listed in Kochi.
        other_city_only = _make_movie("Other City Only", date(2026, 2, 1))
        _add_show(other_city_only, chennai_screen, now + timedelta(days=1))

        # Cancelled in Kochi but bookable in Chennai, so the city and bookable
        # conditions must hold for the same show, not for two different ones.
        cancelled_here = _make_movie("Cancelled Here", date(2026, 2, 1))
        cancelled_show = _add_show(
            cancelled_here, cls.kochi_screen, now + timedelta(days=2)
        )
        Show.objects.filter(pk=cancelled_show.pk).update(status=Show.Status.CANCELLED)
        _add_show(cancelled_here, chennai_screen, now + timedelta(days=2))

        too_late = _make_movie("Too Late", date(2026, 2, 1))
        _add_show(
            too_late, cls.kochi_screen, now - LATE_BOOKING_WINDOW - timedelta(minutes=1)
        )

        # Listed in Kochi.
        just_started = _make_movie("Just Started", date(2026, 1, 1))
        _add_show(just_started, cls.kochi_screen, now - timedelta(minutes=5))

        many_shows = _make_movie("Many Shows", date(2026, 3, 1))
        for days in (3, 4, 5):
            _add_show(many_shows, cls.kochi_screen, now + timedelta(days=days))

    def list_page(self, city: str = "kochi") -> dict:
        """GET the movie list anonymously and return the paginated payload."""
        response = self.client.get(URL, {"city": city})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()["response"]

    def list_titles(self, city: str = "kochi") -> list[str]:
        return [movie["title"] for movie in self.list_page(city)["results"]]

    def test_url_name_resolves_to_api_movies(self):
        self.assertEqual(reverse("movie-list"), URL)

    def test_anonymous_list_is_paginated_inside_envelope(self):
        response = self.client.get(URL, {"city": "kochi"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(set(body), {"hasError", "message", "response"})
        self.assertIs(body["hasError"], False)
        self.assertIsNone(body["message"])

        page = body["response"]
        self.assertEqual(set(page), {"count", "next", "previous", "results"})
        self.assertEqual(page["count"], 3)
        self.assertEqual(len(page["results"]), 3)
        self.assertIsNone(page["next"])
        self.assertIsNone(page["previous"])

    def test_items_contain_exactly_the_public_movie_fields(self):
        results = self.list_page()["results"]

        upcoming = next(item for item in results if item["title"] == "Upcoming")
        self.assertEqual(
            upcoming,
            {
                "publicId": str(self.upcoming.public_id),
                "title": "Upcoming",
                "language": "Malayalam",
                "certificate": "UA",
                "durationMinutes": 120,
                "releaseDate": "2026-02-01",
            },
        )
        for item in results:
            self.assertEqual(set(item), set(upcoming))

    def test_movie_with_upcoming_show_in_city_is_listed(self):
        self.assertIn("Upcoming", self.list_titles())

    def test_movie_showing_only_in_another_city_is_not_listed(self):
        self.assertNotIn("Other City Only", self.list_titles())
        # Sanity check: the fixture's show exists and is bookable.
        self.assertIn("Other City Only", self.list_titles("chennai"))

    def test_movie_whose_only_show_in_city_is_cancelled_is_not_listed(self):
        self.assertNotIn("Cancelled Here", self.list_titles())
        # It is still listed where it has a bookable show.
        self.assertIn("Cancelled Here", self.list_titles("chennai"))

    def test_movie_whose_show_started_before_late_booking_window_is_not_listed(self):
        self.assertNotIn("Too Late", self.list_titles())

    def test_movie_whose_show_started_five_minutes_ago_is_listed(self):
        self.assertLess(timedelta(minutes=5), LATE_BOOKING_WINDOW)
        self.assertIn("Just Started", self.list_titles())

    def test_movie_with_several_shows_in_city_appears_once(self):
        page = self.list_page()
        titles = [movie["title"] for movie in page["results"]]

        self.assertEqual(titles.count("Many Shows"), 1)
        self.assertEqual(page["count"], len(titles))

    def test_results_ordered_by_release_date_desc_then_title(self):
        # Same release date, created out of title order, so the title
        # tie-break can't be confused with id order in either direction.
        starts_at = timezone.now() + timedelta(days=6)
        for title in ("Beta", "Gamma", "Alpha"):
            _add_show(_make_movie(title, date(2026, 4, 1)), self.kochi_screen, starts_at)

        self.assertEqual(
            self.list_titles(),
            ["Alpha", "Beta", "Gamma", "Many Shows", "Upcoming", "Just Started"],
        )

    def test_missing_or_blank_city_returns_400(self):
        for params in ({}, {"city": ""}, {"city": "   "}):
            with self.subTest(params=params):
                response = self.client.get(URL, params)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                body = response.json()
                self.assertIs(body["hasError"], True)
                self.assertEqual(body["code"], ErrorCode.VALIDATION_ERROR)
                self.assertEqual(
                    body["details"],
                    [{"field": "city", "message": "This field is required."}],
                )

    def test_unknown_city_returns_404(self):
        response = self.client.get(URL, {"city": "atlantis"})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = response.json()
        self.assertIs(body["hasError"], True)
        self.assertEqual(body["code"], ErrorCode.NOT_FOUND)
        self.assertEqual(body["message"], "City not found.")

    def test_query_count_does_not_grow_with_movies_or_shows(self):
        # City lookup, pagination COUNT, and the page of movies.
        with self.assertNumQueries(3):
            before = self.list_page()

        starts_at = timezone.now() + timedelta(days=10)
        for i in range(5):
            movie = _make_movie(f"Extra {i}", date(2025, 12, 1))
            for days in range(3):
                _add_show(movie, self.kochi_screen, starts_at + timedelta(days=days))

        with self.assertNumQueries(3):
            after = self.list_page()

        self.assertEqual(after["count"], before["count"] + 5)
