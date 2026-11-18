import threading
from datetime import date, timedelta
from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import User
from bookings.models import ShowSeat, ShowSeatStatus
from bookings.services.holds import hold_seats
from catalog.models import Cinema, City, Movie, Screen, Seat, SeatCategory
from catalog.services import create_show
from core.exceptions import ConflictError

THREAD_COUNT = 20


class HoldSeatsConcurrencyTests(TransactionTestCase):
    """Threads use their own DB connections, so data must really be committed.

    TestCase wraps each test in a transaction the threads could not see;
    TransactionTestCase commits and flushes the tables after each test instead.
    """

    def setUp(self):
        city = City.objects.create(name="Kochi", state="Kerala", slug="kochi")
        cinema = Cinema.objects.create(city=city, name="Test Cinema", address="1 Main St")
        screen = Screen.objects.create(cinema=cinema, name="Screen 1")
        self.seat = Seat.objects.create(
            screen=screen, row="F", number=1, category=SeatCategory.NORMAL
        )
        movie = Movie.objects.create(
            title="Test Movie",
            duration_minutes=120,
            language="English",
            certificate=Movie.Certificate.UA,
            release_date=date(2026, 1, 1),
        )
        self.show = create_show(
            movie=movie,
            screen=screen,
            starts_at=timezone.now() + timedelta(days=1),
            prices={SeatCategory.NORMAL: Decimal("200.00")},
        )
        self.users = [
            User.objects.create_user(
                email=f"user{i}@example.com", password="pass12345", first_name=f"User{i}"
            )
            for i in range(THREAD_COUNT)
        ]

    def test_only_one_of_many_concurrent_holds_wins(self):
        barrier = threading.Barrier(THREAD_COUNT)
        results: list[tuple[str, int]] = []
        results_lock = threading.Lock()

        def attempt(user: User) -> None:
            try:
                barrier.wait(timeout=10)
                try:
                    hold_seats(user=user, show=self.show, seat_ids=[self.seat.id])
                    outcome = "won"
                except ConflictError:
                    outcome = "lost"
                with results_lock:
                    results.append((outcome, user.id))
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(user,)) for user in self.users]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        outcomes = [outcome for outcome, _ in results]
        self.assertEqual(outcomes.count("won"), 1, results)
        self.assertEqual(outcomes.count("lost"), THREAD_COUNT - 1, results)

        winner_id = next(user_id for outcome, user_id in results if outcome == "won")
        show_seat = ShowSeat.objects.get(show=self.show, seat=self.seat)
        self.assertEqual(show_seat.status, ShowSeatStatus.HELD)
        self.assertEqual(show_seat.held_by_id, winner_id)
