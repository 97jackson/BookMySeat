from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User
from bookings.models import ShowSeat, ShowSeatStatus
from bookings.services.holds import (
    HOLD_DURATION,
    LATE_BOOKING_WINDOW,
    MAX_SEATS_PER_HOLD,
    hold_seats,
)
from catalog.models import Cinema, City, Movie, Screen, Seat, SeatCategory, Show
from catalog.services import create_show
from core.error_codes import ErrorCode
from core.exceptions import ConflictError

PRICES = {SeatCategory.NORMAL: Decimal("200.00")}


def _make_screen(cinema: Cinema, name: str) -> dict[str, Seat]:
    """Create a screen with seats F1-F3 and G1-G3; return them keyed by label."""
    screen = Screen.objects.create(cinema=cinema, name=name)
    seats = {}
    for row in ("F", "G"):
        for number in (1, 2, 3):
            seats[f"{row}{number}"] = Seat.objects.create(
                screen=screen, row=row, number=number, category=SeatCategory.NORMAL
            )
    return seats


class HoldSeatsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        city = City.objects.create(name="Kochi", state="Kerala", slug="kochi")
        cinema = Cinema.objects.create(city=city, name="Test Cinema", address="1 Main St")
        cls.seats = _make_screen(cinema, "Screen 1")
        cls.screen = cls.seats["F1"].screen
        cls.movie = Movie.objects.create(
            title="Test Movie",
            duration_minutes=120,
            language="English",
            certificate=Movie.Certificate.UA,
            release_date=date(2026, 1, 1),
        )
        cls.show = create_show(
            movie=cls.movie,
            screen=cls.screen,
            starts_at=timezone.now() + timedelta(days=1),
            prices=PRICES,
        )

        # A second screen with its own show, for the cross-show test.
        cls.other_seats = _make_screen(cinema, "Screen 2")
        cls.other_show = create_show(
            movie=cls.movie,
            screen=cls.other_seats["F1"].screen,
            starts_at=timezone.now() + timedelta(days=1),
            prices=PRICES,
        )

        cls.user_a = User.objects.create_user(
            email="a@example.com", password="pass12345", first_name="A"
        )
        cls.user_b = User.objects.create_user(
            email="b@example.com", password="pass12345", first_name="B"
        )

    def _show_seat(self, label: str, show: Show | None = None) -> ShowSeat:
        return ShowSeat.objects.get(show=show or self.show, seat=self.seats[label])

    def _ids(self, *labels: str) -> list[int]:
        return [self.seats[label].id for label in labels]

    def _assert_free(self, show_seat: ShowSeat) -> None:
        show_seat.refresh_from_db()
        self.assertEqual(show_seat.status, ShowSeatStatus.AVAILABLE)
        self.assertIsNone(show_seat.held_by_id)
        self.assertIsNone(show_seat.held_until)

    def test_hold_two_free_seats_succeeds(self):
        before = timezone.now()
        held_until = hold_seats(user=self.user_a, show=self.show, seat_ids=self._ids("F1", "F2"))
        after = timezone.now()

        self.assertGreaterEqual(held_until, before + HOLD_DURATION)
        self.assertLessEqual(held_until, after + HOLD_DURATION)
        for label in ("F1", "F2"):
            show_seat = self._show_seat(label)
            self.assertEqual(show_seat.status, ShowSeatStatus.HELD)
            self.assertEqual(show_seat.held_by_id, self.user_a.id)
            self.assertEqual(show_seat.held_until, held_until)

    def test_second_user_cannot_hold_same_seats(self):
        seat_ids = self._ids("F1", "F2")
        held_until = hold_seats(user=self.user_a, show=self.show, seat_ids=seat_ids)

        with self.assertRaises(ConflictError) as ctx:
            hold_seats(user=self.user_b, show=self.show, seat_ids=seat_ids)

        self.assertEqual(ctx.exception.get_codes(), ErrorCode.SEATS_UNAVAILABLE)
        for label in ("F1", "F2"):
            show_seat = self._show_seat(label)
            self.assertEqual(show_seat.status, ShowSeatStatus.HELD)
            self.assertEqual(show_seat.held_by_id, self.user_a.id)
            self.assertEqual(show_seat.held_until, held_until)

    def test_hold_is_all_or_nothing(self):
        hold_seats(user=self.user_a, show=self.show, seat_ids=self._ids("F1"))

        with self.assertRaises(ConflictError):
            hold_seats(user=self.user_b, show=self.show, seat_ids=self._ids("F1", "F2"))

        self._assert_free(self._show_seat("F2"))
        self.assertEqual(self._show_seat("F1").held_by_id, self.user_a.id)

    def test_expired_hold_can_be_taken(self):
        ShowSeat.objects.filter(show=self.show, seat=self.seats["F1"]).update(
            status=ShowSeatStatus.HELD,
            held_by=self.user_a,
            held_until=timezone.now() - timedelta(minutes=1),
        )

        held_until = hold_seats(user=self.user_b, show=self.show, seat_ids=self._ids("F1"))

        show_seat = self._show_seat("F1")
        self.assertEqual(show_seat.status, ShowSeatStatus.HELD)
        self.assertEqual(show_seat.held_by_id, self.user_b.id)
        self.assertEqual(show_seat.held_until, held_until)

    def test_empty_seat_list_is_rejected(self):
        with self.assertRaises(ValidationError):
            hold_seats(user=self.user_a, show=self.show, seat_ids=[])

    def test_duplicate_seat_ids_are_rejected(self):
        with self.assertRaises(ValidationError):
            hold_seats(user=self.user_a, show=self.show, seat_ids=self._ids("F1", "F1"))
        self._assert_free(self._show_seat("F1"))

    def test_too_many_seats_are_rejected(self):
        # Validation runs before any DB lookup, so distinct placeholder ids suffice.
        seat_ids = list(range(1, MAX_SEATS_PER_HOLD + 2))
        with self.assertRaises(ValidationError):
            hold_seats(user=self.user_a, show=self.show, seat_ids=seat_ids)

    def test_cancelled_show_is_rejected(self):
        self.show.status = Show.Status.CANCELLED
        self.show.save(update_fields=["status"])

        with self.assertRaises(ConflictError):
            hold_seats(user=self.user_a, show=self.show, seat_ids=self._ids("F1"))
        self._assert_free(self._show_seat("F1"))

    def test_show_past_late_booking_window_is_rejected(self):
        show = create_show(
            movie=self.movie,
            screen=self.screen,
            starts_at=timezone.now() - LATE_BOOKING_WINDOW - timedelta(minutes=1),
            prices=PRICES,
        )

        with self.assertRaises(ConflictError):
            hold_seats(user=self.user_a, show=show, seat_ids=self._ids("F1"))
        self._assert_free(self._show_seat("F1", show=show))

    def test_show_inside_late_booking_window_can_be_held(self):
        starts_at = timezone.now() - timedelta(minutes=5)
        self.assertLess(timedelta(minutes=5), LATE_BOOKING_WINDOW)
        show = create_show(
            movie=self.movie, screen=self.screen, starts_at=starts_at, prices=PRICES
        )

        hold_seats(user=self.user_a, show=show, seat_ids=self._ids("F1"))

        show_seat = self._show_seat("F1", show=show)
        self.assertEqual(show_seat.status, ShowSeatStatus.HELD)
        self.assertEqual(show_seat.held_by_id, self.user_a.id)

    def test_seats_from_another_screen_are_rejected(self):
        # One valid seat of this show plus one seat from a different show's screen.
        seat_ids = [self.seats["F1"].id, self.other_seats["F1"].id]

        with self.assertRaises(ConflictError):
            hold_seats(user=self.user_a, show=self.show, seat_ids=seat_ids)

        self.assertFalse(ShowSeat.objects.filter(status=ShowSeatStatus.HELD).exists())
