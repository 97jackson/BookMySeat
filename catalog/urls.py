from django.urls import path

from catalog.views import CityListView

urlpatterns = [
    path("cities/", CityListView.as_view(), name="city-list"),
]
