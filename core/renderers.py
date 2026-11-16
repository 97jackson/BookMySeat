from rest_framework.renderers import JSONRenderer

from core.camel_case import camelize


class CustomResponseRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = (renderer_context or {}).get("response")
        if response is not None and response.status_code < 400 and data is not None:
            data = {"has_error": False, "message": None, "response": data}
        return super().render(camelize(data), accepted_media_type, renderer_context)