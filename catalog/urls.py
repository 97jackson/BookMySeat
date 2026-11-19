from django.urls import path

from catalog.views import CityListView, MovieListView

urlpatterns = [
    path("cities/", CityListView.as_view(), name="city-list"),
    path("movies/", MovieListView.as_view(), name="movie-list"),
]
