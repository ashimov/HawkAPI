"""Tests for constants module."""

from hawkapi._constants import (
    DEFAULT_CHARSET,
    DEFAULT_CONTENT_TYPE,
    HTTP_STATUS_PHRASES,
    SUPPORTED_METHODS,
)


def test_status_phrases():
    assert HTTP_STATUS_PHRASES[200] == "OK"
    assert HTTP_STATUS_PHRASES[404] == "Not Found"
    assert HTTP_STATUS_PHRASES[500] == "Internal Server Error"


def test_defaults():
    assert DEFAULT_CONTENT_TYPE == b"application/json"
    assert DEFAULT_CHARSET == "utf-8"


def test_supported_methods():
    assert "GET" in SUPPORTED_METHODS
    assert "POST" in SUPPORTED_METHODS
    assert "DELETE" in SUPPORTED_METHODS
    assert "OPTIONS" in SUPPORTED_METHODS
    assert isinstance(SUPPORTED_METHODS, frozenset)
