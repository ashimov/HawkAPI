"""Tests for HTTPException."""

import pytest

from hawkapi.exceptions import HTTPException


def test_http_exception_basic():
    exc = HTTPException(404, detail="Not found")
    assert exc.status_code == 404
    assert exc.detail == "Not found"
    assert exc.headers is None


def test_http_exception_with_headers():
    exc = HTTPException(401, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"})
    assert exc.headers == {"WWW-Authenticate": "Bearer"}


def test_http_exception_to_response():
    exc = HTTPException(403, detail="Forbidden")
    response = exc.to_response()
    assert response.status_code == 403
    assert b"Forbidden" in response.body
    assert response.content_type == "application/problem+json"


def test_http_exception_to_response_with_headers():
    exc = HTTPException(401, detail="No token", headers={"X-Reason": "missing"})
    response = exc.to_response()
    assert response.status_code == 401
    assert response.headers == {"X-Reason": "missing"}


def test_http_exception_is_exception():
    with pytest.raises(HTTPException) as exc_info:
        raise HTTPException(500, detail="Boom")
    assert exc_info.value.status_code == 500


def test_http_exception_no_detail():
    exc = HTTPException(400)
    response = exc.to_response()
    assert response.status_code == 400
    assert b"detail" not in response.body
