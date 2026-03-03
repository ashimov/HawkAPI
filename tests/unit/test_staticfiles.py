"""Tests for StaticFiles."""

import pytest

from hawkapi.staticfiles import StaticFiles


@pytest.fixture
def static_dir(tmp_path):
    """Create a temporary static directory with files."""
    (tmp_path / "hello.txt").write_text("Hello, World!")
    (tmp_path / "style.css").write_text("body { color: red; }")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "page.html").write_text("<h1>Page</h1>")
    (sub / "index.html").write_text("<h1>Index</h1>")
    return tmp_path


def _make_scope(path="/", method="GET"):
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("localhost", 8000),
    }


async def _collect(app, scope):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        messages.append(msg)

    await app(scope, receive, send)
    return messages


async def test_serve_file(static_dir):
    app = StaticFiles(directory=static_dir)
    msgs = await _collect(app, _make_scope("/hello.txt"))
    assert msgs[0]["status"] == 200
    body = b"".join(m.get("body", b"") for m in msgs if m["type"] == "http.response.body")
    assert body == b"Hello, World!"


async def test_serve_nested_file(static_dir):
    app = StaticFiles(directory=static_dir)
    msgs = await _collect(app, _make_scope("/sub/page.html"))
    assert msgs[0]["status"] == 200


async def test_file_not_found(static_dir):
    app = StaticFiles(directory=static_dir)
    msgs = await _collect(app, _make_scope("/nonexistent.txt"))
    assert msgs[0]["status"] == 404


async def test_path_traversal_blocked(static_dir):
    app = StaticFiles(directory=static_dir)
    msgs = await _collect(app, _make_scope("/../../../etc/passwd"))
    assert msgs[0]["status"] == 404


async def test_method_not_allowed(static_dir):
    app = StaticFiles(directory=static_dir)
    msgs = await _collect(app, _make_scope("/hello.txt", method="POST"))
    assert msgs[0]["status"] == 405


async def test_head_request(static_dir):
    app = StaticFiles(directory=static_dir)
    msgs = await _collect(app, _make_scope("/hello.txt", method="HEAD"))
    assert msgs[0]["status"] == 200


async def test_html_mode_index(static_dir):
    app = StaticFiles(directory=static_dir, html=True)
    msgs = await _collect(app, _make_scope("/sub/"))
    assert msgs[0]["status"] == 200
    body = b"".join(m.get("body", b"") for m in msgs if m["type"] == "http.response.body")
    assert b"Index" in body


async def test_html_mode_no_index(static_dir):
    # Directory without index.html when html=False
    app = StaticFiles(directory=static_dir, html=False)
    msgs = await _collect(app, _make_scope("/sub/"))
    assert msgs[0]["status"] == 404


async def test_invalid_directory():
    with pytest.raises(RuntimeError, match="Static directory not found"):
        StaticFiles(directory="/nonexistent/path")


async def test_non_http_scope(static_dir):
    app = StaticFiles(directory=static_dir)
    scope = {"type": "websocket", "path": "/hello.txt"}
    msgs = await _collect(app, scope)
    assert len(msgs) == 0
