import json

from sqlalchemy.types import Text, TypeDecorator


class JSONEncodedList(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None

        if isinstance(value, str):
            return value

        return json.dumps(list(value), ensure_ascii=True)

    def process_result_value(self, value, dialect):
        if value in (None, ""):
            return None

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None

        if not isinstance(parsed, list):
            return None

        normalized: list[str] = []

        for item in parsed:
            text = str(item).strip()
            if text:
                normalized.append(text)

        return normalized
