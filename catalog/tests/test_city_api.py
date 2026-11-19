from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import City

URL = "/api/cities/"

TRIVANDRUM = {"name": "Trivandrum", "state": "Kerala", "slug": "trivandrum"}
KOCHI = {"name": "Kochi", "state": "Kerala", "slug": "kochi"}
CHENNAI = {"name": "Chennai", "state": "Tamil Nadu", "slug": "chennai"}


class CityListAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Created out of alphabetical order so the ordering assertions mean something.
        for city in (TRIVANDRUM, CHENNAI, KOCHI):
            City.objects.create(**city)

    def get(self, params=None):
        """GET the city list anonymously, asserting it costs exactly one query."""
        with self.assertNumQueries(1):
            response = self.client.get(URL, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()

    def test_url_name_resolves_to_api_cities(self):
        self.assertEqual(reverse("city-list"), URL)

    def test_anonymous_list_returns_all_cities_sorted_in_envelope(self):
        body = self.get()

        self.assertEqual(set(body), {"hasError", "message", "response"})
        self.assertIs(body["hasError"], False)
        self.assertIsNone(body["message"])
        # Full equality pins both the ordering and the exact keys on each item.
        self.assertEqual(body["response"], [CHENNAI, KOCHI, TRIVANDRUM])

    def test_response_is_plain_list_not_paginated(self):
        body = self.get()

        self.assertIsInstance(body["response"], list)
        self.assertNotIn("count", body)
        self.assertNotIn("results", body)

    def test_search_by_name_partial_match(self):
        body = self.get({"search": "triv"})

        self.assertEqual(body["response"], [TRIVANDRUM])

    def test_search_is_case_insensitive(self):
        body = self.get({"search": "TRIV"})

        self.assertEqual(body["response"], [TRIVANDRUM])

    def test_search_by_state_returns_matching_cities_sorted(self):
        body = self.get({"search": "kerala"})

        self.assertEqual(body["response"], [KOCHI, TRIVANDRUM])

    def test_search_with_no_match_returns_empty_list(self):
        body = self.get({"search": "xyz"})

        self.assertIs(body["hasError"], False)
        self.assertEqual(body["response"], [])
