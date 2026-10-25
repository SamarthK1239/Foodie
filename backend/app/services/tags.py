"""JSON list columns (recipe tags, meat types).

These live outside the API layer because both the serializers and the classifier
need them, and the classifier must not import from `app.api`.
"""

from __future__ import annotations

import json


def load_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return [t.strip() for t in raw.split(",") if t.strip()]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def dump_tags(tags: list[str] | None) -> str | None:
    if tags is None:
        return None
    return json.dumps(sorted({t.strip() for t in tags if t and t.strip()}))
