"""JSON serialization helpers for API and CLI output."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Convert dataclasses, Decimals, tuples, and dictionaries to JSON values."""

    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value
