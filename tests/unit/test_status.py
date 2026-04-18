"""Tests for ``hawkapi.status`` — HTTP and WebSocket status-code constants.

The module mirrors Starlette's ``starlette.status`` namespace so that code
migrated from FastAPI (which re-exports the Starlette module) continues to
work without edits. The actual integer values come from Python's
``http.HTTPStatus`` enum and RFC 6455 section 7.4.
"""

from __future__ import annotations


def test_status_module_importable_from_package() -> None:
    from hawkapi import status

    assert status.HTTP_200_OK == 200


def test_status_constants_importable_directly() -> None:
    from hawkapi.status import HTTP_200_OK, HTTP_404_NOT_FOUND

    assert HTTP_200_OK == 200
    assert HTTP_404_NOT_FOUND == 404


def test_common_http_values() -> None:
    from hawkapi import status

    # A representative sampling across 2xx/3xx/4xx/5xx.
    assert status.HTTP_200_OK == 200
    assert status.HTTP_201_CREATED == 201
    assert status.HTTP_204_NO_CONTENT == 204
    assert status.HTTP_301_MOVED_PERMANENTLY == 301
    assert status.HTTP_302_FOUND == 302
    assert status.HTTP_400_BAD_REQUEST == 400
    assert status.HTTP_401_UNAUTHORIZED == 401
    assert status.HTTP_403_FORBIDDEN == 403
    assert status.HTTP_404_NOT_FOUND == 404
    assert status.HTTP_409_CONFLICT == 409
    assert status.HTTP_422_UNPROCESSABLE_ENTITY == 422
    assert status.HTTP_500_INTERNAL_SERVER_ERROR == 500
    assert status.HTTP_502_BAD_GATEWAY == 502
    assert status.HTTP_503_SERVICE_UNAVAILABLE == 503


def test_starlette_compat_overrides() -> None:
    """Three codes keep Starlette's older names even though Python's enum was renamed."""
    from hawkapi import status

    assert status.HTTP_413_REQUEST_ENTITY_TOO_LARGE == 413
    assert status.HTTP_414_REQUEST_URI_TOO_LONG == 414
    assert status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE == 416


def test_websocket_close_codes() -> None:
    from hawkapi import status

    assert status.WS_1000_NORMAL_CLOSURE == 1000
    assert status.WS_1001_GOING_AWAY == 1001
    assert status.WS_1002_PROTOCOL_ERROR == 1002
    assert status.WS_1003_UNSUPPORTED_DATA == 1003
    assert status.WS_1005_NO_STATUS_RCVD == 1005
    assert status.WS_1006_ABNORMAL_CLOSURE == 1006
    assert status.WS_1007_INVALID_FRAME_PAYLOAD_DATA == 1007
    assert status.WS_1008_POLICY_VIOLATION == 1008
    assert status.WS_1009_MESSAGE_TOO_BIG == 1009
    assert status.WS_1010_MANDATORY_EXT == 1010
    assert status.WS_1011_INTERNAL_ERROR == 1011
    assert status.WS_1012_SERVICE_RESTART == 1012
    assert status.WS_1013_TRY_AGAIN_LATER == 1013
    assert status.WS_1014_BAD_GATEWAY == 1014
    assert status.WS_1015_TLS_HANDSHAKE == 1015


def test_all_includes_every_public_name() -> None:
    """``__all__`` must list every HTTP_* and WS_* constant exported by the module."""
    from hawkapi import status

    public_names = {n for n in dir(status) if n.startswith(("HTTP_", "WS_"))}
    assert public_names, "no constants found — module is empty"
    assert set(status.__all__) == public_names
