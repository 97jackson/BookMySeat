from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import override_settings
from django.urls import path
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APITestCase
from rest_framework.views import APIView

from core.error_codes import ErrorCode
from core.exceptions import ConflictError


class PersonSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class AddressSerializer(serializers.Serializer):
    postal_code = serializers.CharField()


class OrderSerializer(serializers.Serializer):
    billing_address = AddressSerializer()


class LineItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class CartSerializer(serializers.Serializer):
    line_items = LineItemSerializer(many=True)


class TaggedSerializer(serializers.Serializer):
    seat_tags = serializers.ListField(child=serializers.CharField())


class _OpenView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]


class MissingFieldsView(_OpenView):
    def get(self, request):
        PersonSerializer(data={}).is_valid(raise_exception=True)


class NestedErrorView(_OpenView):
    def get(self, request):
        OrderSerializer(data={"billing_address": {}}).is_valid(raise_exception=True)


class ListItemErrorsView(_OpenView):
    def get(self, request):
        data = {"line_items": [{"quantity": 1}, {}, {"quantity": 0}]}
        CartSerializer(data=data).is_valid(raise_exception=True)


class ListFieldErrorView(_OpenView):
    def get(self, request):
        TaggedSerializer(data={"seat_tags": ["aisle", ""]}).is_valid(raise_exception=True)


class PlainValidationView(_OpenView):
    def get(self, request):
        raise ValidationError("plain message")


class DrfNotFoundView(_OpenView):
    def get(self, request):
        raise NotFound("Order not found.")


class DjangoHttp404View(_OpenView):
    def get(self, request):
        raise Http404


class DjangoPermissionDeniedView(_OpenView):
    def get(self, request):
        raise PermissionDenied


class SoldOutView(_OpenView):
    def get(self, request):
        raise ConflictError("Only 2 tickets left.", code=ErrorCode.SOLD_OUT)


class SuccessView(_OpenView):
    def get(self, request):
        return Response({"booking_id": 1})


urlpatterns = [
    path("missing-fields/", MissingFieldsView.as_view()),
    path("nested-error/", NestedErrorView.as_view()),
    path("list-item-errors/", ListItemErrorsView.as_view()),
    path("list-field-error/", ListFieldErrorView.as_view()),
    path("plain-validation/", PlainValidationView.as_view()),
    path("drf-not-found/", DrfNotFoundView.as_view()),
    path("django-404/", DjangoHttp404View.as_view()),
    path("django-permission-denied/", DjangoPermissionDeniedView.as_view()),
    path("sold-out/", SoldOutView.as_view()),
    path("success/", SuccessView.as_view()),
]


@override_settings(ROOT_URLCONF=__name__)
class ErrorResponseFormatTests(APITestCase):
    def test_missing_required_fields(self):
        response = self.client.get("/missing-fields/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "hasError": True,
                "status": 400,
                "code": "validation_error",
                "message": "Please correct the highlighted fields.",
                "details": [
                    {"field": "firstName", "message": "First name is required."},
                    {"field": "lastName", "message": "Last name is required."},
                ],
                "response": None,
            },
        )

    def test_nested_error_uses_dotted_camel_case_path(self):
        response = self.client.get("/nested-error/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "hasError": True,
                "status": 400,
                "code": "validation_error",
                "message": "Please correct the highlighted fields.",
                "details": [
                    {
                        "field": "billingAddress.postalCode",
                        "message": "Postal code is required.",
                    },
                ],
                "response": None,
            },
        )

    def test_list_item_errors_include_item_index(self):
        response = self.client.get("/list-item-errors/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "hasError": True,
                "status": 400,
                "code": "validation_error",
                "message": "Please correct the highlighted fields.",
                "details": [
                    {"field": "lineItems.1.quantity", "message": "Quantity is required."},
                    {
                        "field": "lineItems.2.quantity",
                        "message": "Ensure this value is greater than or equal to 1.",
                    },
                ],
                "response": None,
            },
        )

    def test_list_field_error_labels_skip_index(self):
        response = self.client.get("/list-field-error/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["details"],
            [{"field": "seatTags.1", "message": "Seat tags is required."}],
        )

    def test_plain_validation_error_has_null_field(self):
        response = self.client.get("/plain-validation/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "hasError": True,
                "status": 400,
                "code": "validation_error",
                "message": "plain message",
                "details": [{"field": None, "message": "plain message"}],
                "response": None,
            },
        )

    def test_drf_not_found(self):
        response = self.client.get("/drf-not-found/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "hasError": True,
                "status": 404,
                "code": "not_found",
                "message": "Order not found.",
                "details": [],
                "response": None,
            },
        )

    def test_django_http404(self):
        response = self.client.get("/django-404/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "hasError": True,
                "status": 404,
                "code": "not_found",
                "message": "Not found.",
                "details": [],
                "response": None,
            },
        )

    def test_django_permission_denied(self):
        response = self.client.get("/django-permission-denied/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "hasError": True,
                "status": 403,
                "code": "permission_denied",
                "message": "You do not have permission to perform this action.",
                "details": [],
                "response": None,
            },
        )

    def test_custom_code_on_conflict_error(self):
        response = self.client.get("/sold-out/")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {
                "hasError": True,
                "status": 409,
                "code": "sold_out",
                "message": "Only 2 tickets left.",
                "details": [],
                "response": None,
            },
        )

    def test_success_format_unchanged(self):
        response = self.client.get("/success/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"hasError": False, "message": None, "response": {"bookingId": 1}},
        )


class LoginErrorResponseTests(APITestCase):
    def test_login_with_empty_body(self):
        response = self.client.post("/api/auth/login/", {}, format="json")

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["status"], 400)
        self.assertEqual(body["code"], "validation_error")
        self.assertEqual(body["message"], "Please correct the highlighted fields.")
        self.assertIn({"field": "email", "message": "Email is required."}, body["details"])
        self.assertIn(
            {"field": "password", "message": "Password is required."}, body["details"]
        )
