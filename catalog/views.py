from rest_framework import filters, generics
from rest_framework.permissions import AllowAny

from catalog.models import City
from catalog.serializers import CitySerializer


class CityListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    pagination_class = None
    queryset = City.objects.order_by("name")
    serializer_class = CitySerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "state"]
