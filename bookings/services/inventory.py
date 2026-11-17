from bookings.models import ShowSeat, ShowSeatStatus
from catalog.models import Seat, Show


def create_show_seats(show: Show) -> int:
    """Create one AVAILABLE ShowSeat per seat on the show's screen.

    Returns the number of rows created.
    """
    seat_ids = Seat.objects.filter(screen_id=show.screen_id).values_list("id", flat=True)
    show_seats = [
        ShowSeat(show=show, seat_id=seat_id, status=ShowSeatStatus.AVAILABLE)
        for seat_id in seat_ids
    ]
    return len(ShowSeat.objects.bulk_create(show_seats))
