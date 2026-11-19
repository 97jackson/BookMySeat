from rest_framework import serializers

from catalog.models import City


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["name", "state", "slug"]
