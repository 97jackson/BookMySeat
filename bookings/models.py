from django.conf import settings
from django.db import models
from django.db.models import Q

from catalog.models import Seat, Show
from core.models import BaseModel


# Module level (not nested in ShowSeat) so Meta.constraints can reference it:
# a nested class body cannot see names from the enclosing class body.
class ShowSeatStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    HELD = "held", "Held"
    BOOKED = "booked", "Booked"


class ShowSeat(BaseModel):
    show = models.ForeignKey(Show, on_delete=models.PROTECT, related_name="show_seats")
    seat = models.ForeignKey(Seat, on_delete=models.PROTECT, related_name="show_seats")
    status = models.CharField(
        max_length=20,
        choices=ShowSeatStatus.choices,
        default=ShowSeatStatus.AVAILABLE,
    )
    held_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="held_seats",
    )
    held_until = models.DateTimeField(null=True, blank=True)

    # Type-only hints for the attributes Django adds at runtime for each FK.
    # Bare annotations don't create fields; they just inform Pylance/Pyright.
    show_id: int
    seat_id: int
    held_by_id: int | None

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["show", "seat"],
                name="bookings_showseat_unique_show_seat",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=ShowSeatStatus.HELD,
                        held_by__isnull=False,
                        held_until__isnull=False,
                    )
                    | (~Q(status=ShowSeatStatus.HELD) & Q(held_until__isnull=True))
                ),
                name="bookings_showseat_hold_fields_match_status",
            ),
        ]
        indexes = [
            # Django caps index names at 30 characters (models.E034).
            models.Index(
                fields=["show", "status"],
                name="bookings_ss_show_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.seat_id} for show {self.show_id}: {self.status}"
