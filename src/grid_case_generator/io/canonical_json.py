"""Deterministic in-memory JSON serialization for Canonical values."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


def to_canonical_data(value: object) -> Any:
    """Convert a Canonical value to JSON-compatible data without losing precision."""

    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, str):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise TypeError("non-finite Decimal values are not valid Canonical JSON")
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        raise TypeError("float values are not valid Canonical JSON")
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_canonical_data(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [to_canonical_data(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Canonical JSON object keys must be strings")
        return {str(key): to_canonical_data(item) for key, item in value.items()}
    raise TypeError(f"unsupported Canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a Canonical value to stable UTF-8 JSON bytes."""

    return json.dumps(
        to_canonical_data(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
