"""HTTP and WebSocket status-code constants.

Usage::

    from hawkapi import status

    @app.post("/items", status_code=status.HTTP_201_CREATED)

Names match Starlette's ``starlette.status`` namespace exactly so code
migrated from FastAPI (which re-exports the Starlette module) keeps working
without edits. Integer values come from the stdlib ``http.HTTPStatus`` enum
for HTTP codes and RFC 6455 section 7.4 for WebSocket close codes.
"""

from __future__ import annotations

from http import HTTPStatus as _HTTPStatus

# Python 3.12 renamed three HTTPStatus members to align with RFC 9110. Keep
# Starlette's older spelling so FastAPI migrators don't need to rewrite code.
_STARLETTE_OVERRIDES: dict[int, str] = {
    413: "HTTP_413_REQUEST_ENTITY_TOO_LARGE",  # stdlib (3.12+): CONTENT_TOO_LARGE
    414: "HTTP_414_REQUEST_URI_TOO_LONG",  # stdlib (3.12+): URI_TOO_LONG
    416: "HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE",  # stdlib (3.12+): RANGE_NOT_SATISFIABLE
    422: "HTTP_422_UNPROCESSABLE_ENTITY",  # stdlib (3.13+): UNPROCESSABLE_CONTENT
}


def _generate_http_constants() -> None:
    """Populate module globals with ``HTTP_<code>_<NAME>`` integers."""
    for code in _HTTPStatus:
        name = _STARLETTE_OVERRIDES.get(code.value, f"HTTP_{code.value}_{code.name}")
        globals()[name] = code.value


_generate_http_constants()
del _generate_http_constants

# WebSocket close codes (RFC 6455 section 7.4 + common extensions).
WS_1000_NORMAL_CLOSURE = 1000
WS_1001_GOING_AWAY = 1001
WS_1002_PROTOCOL_ERROR = 1002
WS_1003_UNSUPPORTED_DATA = 1003
WS_1005_NO_STATUS_RCVD = 1005
WS_1006_ABNORMAL_CLOSURE = 1006
WS_1007_INVALID_FRAME_PAYLOAD_DATA = 1007
WS_1008_POLICY_VIOLATION = 1008
WS_1009_MESSAGE_TOO_BIG = 1009
WS_1010_MANDATORY_EXT = 1010
WS_1011_INTERNAL_ERROR = 1011
WS_1012_SERVICE_RESTART = 1012
WS_1013_TRY_AGAIN_LATER = 1013
WS_1014_BAD_GATEWAY = 1014
WS_1015_TLS_HANDSHAKE = 1015


# __all__ is built from globals() populated by _generate_http_constants() above.
# Pyright cannot statically verify a dynamic __all__; suppress the diagnostic.
__all__: list[str] = sorted(  # pyright: ignore[reportUnsupportedDunderAll]
    name for name in globals() if name.startswith(("HTTP_", "WS_"))
)
