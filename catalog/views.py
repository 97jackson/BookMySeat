from rest_framework import filters, generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny

from catalog.models import City, Movie, Show
from catalog.serializers import CitySerializer, MovieListSerializer


class CityListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    pagination_class = None
    queryset = City.objects.order_by("name")
    serializer_class = CitySerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "state"]


class MovieListView(generics.ListAPIView):
    """Movies with at least one bookable show in the given city (?city=<slug>)."""

    permission_classes = [AllowAny]
    serializer_class = MovieListSerializer

    def get_queryset(self): 
        slug = self.request.query_params.get("city", "").strip()
        if not slug:
            raise ValidationError({"city": "This field is required."})

        try:
            city = City.objects.get(slug=slug)
        except City.DoesNotExist:
            raise NotFound("City not found.") from None

        # A subquery rather than a join, so each movie appears once without DISTINCT.
        showing = Show.objects.bookable().filter(screen__cinema__city=city)
        return Movie.objects.filter(id__in=showing.values("movie_id")).order_by(
            "-release_date", "title"
        ) 
