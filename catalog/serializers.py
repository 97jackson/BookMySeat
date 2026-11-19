from rest_framework import serializers

from catalog.models import City, Movie


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["name", "state", "slug"]


class MovieListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Movie
        fields = [
            "public_id",
            "title",
            "language",
            "certificate",
            "duration_minutes",
            "release_date",
        ]
