"""Response body encoding using msgspec."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import msgspec

_encoder = msgspec.json.Encoder()


def _enc_hook(obj: Any) -> Any:
    """Fallback encoder for types msgspec doesn't handle natively."""
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
    if isinstance(obj, bytes):
        import base64

        return base64.b64encode(obj).decode("ascii")
    raise TypeError(f"Cannot serialize object of type {type(obj)}")


_encoder_with_hook = msgspec.json.Encoder(enc_hook=_enc_hook)


def encode_response(data: Any) -> bytes:
    """Encode data to JSON bytes. Uses fast path for msgspec types, fallback for others."""
    try:
        return _encoder.encode(data)
    except TypeError:
        return _encoder_with_hook.encode(data)
