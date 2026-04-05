"""Content negotiation — choose response format based on Accept header.

Supports JSON (default), with extensible format registry.
"""

from __future__ import annotations

from typing import Any

from hawkapi.serialization.encoder import encode_response, encode_response_msgpack

# Format registry: media_type -> (encoder, content_type)
_FORMATS: dict[str, tuple[Any, str]] = {
    "application/json": (encode_response, "application/json"),
    "application/msgpack": (encode_response_msgpack, "application/msgpack"),
    "application/x-msgpack": (encode_response_msgpack, "application/x-msgpack"),
}


def negotiate_content_type(accept_header: str | None) -> str:
    """Parse Accept header and return the best supported content type.

    Returns 'application/json' as default.
    """
    if not accept_header:
        return "application/json"

    # Parse accept header with quality values
    accepted: list[tuple[str, float]] = []
    for item in accept_header.split(","):
        item = item.strip()
        if ";" in item:
            media, _, params = item.partition(";")
            # Parse quality factor tolerantly (handles spaces around q=)
            import re

            q_match = re.search(r"q\s*=\s*([0-9.]+)", params, re.IGNORECASE)
            quality = float(q_match.group(1)) if q_match else 1.0
            accepted.append((media.strip(), quality))
        else:
            accepted.append((item.strip(), 1.0))

    # Sort by quality (highest first)
    accepted.sort(key=lambda x: x[1], reverse=True)

    for media, _ in accepted:
        if media in _FORMATS:
            return media
        if media == "*/*":
            return "application/json"

    return "application/json"


def encode_for_content_type(data: Any, content_type: str) -> bytes:
    """Encode data for the given content type."""
    if content_type == "application/json" or content_type not in _FORMATS:
        return encode_response(data)

    encoder, _ = _FORMATS[content_type]
    if encoder is None:
        # Fallback to JSON if encoder not available
        return encode_response(data)
    return encoder(data)
