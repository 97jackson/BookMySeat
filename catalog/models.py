from django.db import models
from django.db.models import F, Q

from core.models import BaseModel


class SeatCategory(models.TextChoices):
    RECLINER = "recliner", "Recliner"
    PREMIUM = "premium", "Premium"
    EXECUTIVE = "executive", "Executive"
    NORMAL = "normal", "Normal"


class City(BaseModel):
    name = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["name", "state"],
                name="catalog_city_unique_name_state",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name}, {self.state}"


class Movie(BaseModel):
    class Certificate(models.TextChoices):
        U = "U", "U"
        UA = "UA", "UA"
        A = "A", "A"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveSmallIntegerField()
    language = models.CharField(max_length=50)
    certificate = models.CharField(max_length=4, choices=Certificate.choices)
    release_date = models.DateField()

    def __str__(self) -> str:
        return self.title


class Cinema(BaseModel):
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="cinemas")
    name = models.CharField(max_length=200)
    address = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self) -> str:
        return self.name


class Screen(BaseModel):
    cinema = models.ForeignKey(Cinema, on_delete=models.CASCADE, related_name="screens")
    name = models.CharField(max_length=50)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["cinema", "name"],
                name="catalog_screen_unique_cinema_name",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.cinema.name} - {self.name}"


class Seat(BaseModel):
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name="seats")
    row = models.CharField(max_length=3)
    number = models.PositiveSmallIntegerField()
    category = models.CharField(max_length=20, choices=SeatCategory.choices)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["screen", "row", "number"],
                name="catalog_seat_unique_screen_row_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.row}{self.number}"


class Show(BaseModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELLED = "cancelled", "Cancelled"

    movie = models.ForeignKey(Movie, on_delete=models.PROTECT, related_name="shows")
    screen = models.ForeignKey(Screen, on_delete=models.PROTECT, related_name="shows")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED
    )

    class Meta(BaseModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="catalog_show_ends_after_starts",
            ),
        ]
        indexes = [
            models.Index(
                fields=["movie", "starts_at"],
                name="catalog_show_movie_starts_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.movie.title} @ {self.starts_at:%Y-%m-%d %H:%M}"


class ShowPrice(BaseModel):
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name="prices")
    category = models.CharField(max_length=20, choices=SeatCategory.choices)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["show", "category"],
                name="catalog_showprice_unique_show_category",
            ),
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name="catalog_showprice_price_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category}: {self.price}"
