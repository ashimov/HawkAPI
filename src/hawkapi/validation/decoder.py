"""Request body decoding using cached msgspec decoders."""

from __future__ import annotations

from typing import Any

import msgspec

from hawkapi._types import Receive
from hawkapi.requests.request import read_body
from hawkapi.validation.errors import (
    RequestValidationError,
    ValidationErrorDetail,
    format_msgspec_error,
)

# Cache decoders per struct type — created once, reused for all requests
_decoder_cache: dict[type, msgspec.json.Decoder[Any]] = {}


def get_decoder(struct_type: type) -> msgspec.json.Decoder[Any]:
    """Get or create a cached JSON decoder for a given type."""
    decoder: msgspec.json.Decoder[Any] | None = _decoder_cache.get(struct_type)
    if decoder is None:
        decoder = msgspec.json.Decoder(struct_type)
        _decoder_cache[struct_type] = decoder
    return decoder


async def decode_body(receive: Receive, struct_type: type) -> Any:
    """Read and decode the request body into a msgspec Struct."""
    body = await read_body(receive)
    if not body:
        raise RequestValidationError(
            [ValidationErrorDetail(field="$", message="Request body is empty", value=None)]
        )
    return decode_bytes(body, struct_type)


def decode_bytes(data: bytes, struct_type: type) -> Any:
    """Decode bytes into the specified type."""
    decoder = get_decoder(struct_type)
    try:
        return decoder.decode(data)
    except msgspec.ValidationError as exc:
        errors = format_msgspec_error(exc)
        raise RequestValidationError(errors) from exc
