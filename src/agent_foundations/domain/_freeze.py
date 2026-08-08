import math
from collections.abc import Iterator, Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any

_JSON_LEAF_TYPES = (str, int, bool, type(None))


class FrozenJSON(Mapping[str, Any]):
    """Immutable, JSON-safe mapping with recursive freeze on construction.

    Accepts only JSON-compatible values: str, int, float, bool, None,
    dict, and list.  dict values are automatically frozen into nested
    FrozenJSON instances; list items are frozen into tuples.
    """

    __slots__ = ("_data",)

    if TYPE_CHECKING:
        _data: dict[str, Any]

    def __init__(self, data: dict[str, Any]) -> None:
        frozen: dict[str, Any] = {}
        for k, v in data.items():
            if not isinstance(k, str):
                raise ValueError(
                    f"FrozenJSON keys must be str, got {type(k).__name__}"
                )
            frozen[k] = _freeze_json_value(v)
        object.__setattr__(self, "_data", frozen)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FrozenJSON):
            return self._data == other._data
        if isinstance(other, Mapping):
            return dict(self) == dict(other)
        return NotImplemented

    def __repr__(self) -> str:
        return f"FrozenJSON({self._data!r})"

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> "FrozenJSON":
        if memo is None:
            memo = {}
        copied = FrozenJSON.__new__(FrozenJSON)
        memo[id(self)] = copied
        object.__setattr__(
            copied,
            "_data",
            {k: deepcopy(v, memo) for k, v in self._data.items()},
        )
        return copied


def _freeze_json_value(value: Any) -> Any:
    """Recursively freeze a single JSON value.

    dict  → FrozenJSON
    list  → tuple (with recursively frozen items)
    str / int / float / bool / None → pass through
    Anything else raises ValueError.
    """
    if isinstance(value, dict):
        return FrozenJSON(value)
    if isinstance(value, list):
        return tuple(_freeze_json_value(v) for v in value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"value must be a finite JSON number, got {value!r}")
        return value
    if isinstance(value, _JSON_LEAF_TYPES):
        return value
    raise ValueError(
        f"value must be JSON-compatible (str, int, float, bool, None,"
        f" dict, list), got {type(value).__name__}"
    )


def _validate_freeze_dict(value: Any) -> FrozenJSON:
    if isinstance(value, FrozenJSON):
        return value
    if isinstance(value, dict):
        return FrozenJSON(value)
    raise ValueError(f"expected dict, got {type(value).__name__}")


def _validate_freeze_dict_or_none(value: Any) -> FrozenJSON | None:
    if value is None:
        return None
    if isinstance(value, FrozenJSON):
        return value
    if isinstance(value, dict):
        return FrozenJSON(value)
    raise ValueError(f"expected dict or None, got {type(value).__name__}")


def _serialize_frozen(value: Any) -> Any:
    """Convert frozen structures to plain JSON-serializable Python objects."""
    if isinstance(value, FrozenJSON):
        return {k: _serialize_frozen(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_serialize_frozen(v) for v in value]
    return value


def to_json_value(value: Any) -> Any:
    """Return plain dict/list containers suitable for SDKs and JSON Schema.

    FrozenJSON → dict, tuple → list.  Leaf values pass through unchanged.
    """
    if isinstance(value, Mapping):
        return {key: to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    return value
