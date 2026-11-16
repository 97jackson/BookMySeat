from rest_framework.parsers import JSONParser

from core.camel_case import decamelize


class CamelCaseJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)
        return decamelize(data)