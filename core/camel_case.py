import re

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def to_camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest)


def to_snake(name: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def camelize(data):
    if isinstance(data, dict):
        return {
            to_camel(key) if isinstance(key, str) else key: camelize(value)
            for key, value in data.items()
        }
    if isinstance(data, (list, tuple)):
        return [camelize(item) for item in data]
    return data


def decamelize(data):
    if isinstance(data, dict):
        return {
            to_snake(key) if isinstance(key, str) else key: decamelize(value)
            for key, value in data.items()
        }
    if isinstance(data, (list, tuple)):
        return [decamelize(item) for item in data]
    return data