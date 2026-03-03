"""Tests for validation constraints markers."""

from hawkapi.validation.constraints import Body, Cookie, Header, Path, Query


def test_path_marker():
    p = Path(alias="user_id", description="The user ID")
    assert p.alias == "user_id"
    assert p.description == "The user ID"
    assert not p.has_default()


def test_query_marker_with_default():
    q = Query(default=10, description="Page number")
    assert q.has_default() is True
    assert q.get_default() == 10


def test_query_marker_with_factory():
    q = Query(default_factory=list)
    assert q.has_default() is True
    assert q.get_default() == []


def test_header_marker():
    h = Header(alias="x-token")
    assert h.alias == "x-token"
    assert not h.has_default()


def test_body_marker():
    b = Body(description="Request body")
    assert b.description == "Request body"


def test_cookie_marker():
    c = Cookie(alias="session_id", default="none")
    assert c.alias == "session_id"
    assert c.has_default() is True
    assert c.get_default() == "none"


def test_marker_no_default():
    p = Path()
    assert p.has_default() is False
    assert p.get_default() is ...  # Ellipsis
