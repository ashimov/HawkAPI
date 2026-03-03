"""Extra tests for Request covering uncovered branches."""

from hawkapi.requests.request import Request, _parse_cookies


def _make_scope(
    path="/",
    method="GET",
    headers=None,
    query_string=b"",
    scheme="https",
    client=None,
):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "root_path": "",
        "headers": headers or [],
        "server": ("localhost", 8000),
        "scheme": scheme,
    }
    if client:
        scope["client"] = client
    return scope


async def _noop_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def test_method():
    req = Request(_make_scope(method="POST"), _noop_receive)
    assert req.method == "POST"


def test_path():
    req = Request(_make_scope(path="/users/42"), _noop_receive)
    assert req.path == "/users/42"


def test_query_string():
    req = Request(_make_scope(query_string=b"a=1&b=2"), _noop_receive)
    assert req.query_string == b"a=1&b=2"


def test_url_scheme():
    req = Request(_make_scope(scheme="https"), _noop_receive)
    assert req.url_scheme == "https"


def test_client_info():
    req = Request(_make_scope(client=("127.0.0.1", 54321)), _noop_receive)
    assert req.client == ("127.0.0.1", 54321)


def test_client_none():
    req = Request(_make_scope(), _noop_receive)
    assert req.client is None


def test_content_type():
    req = Request(
        _make_scope(headers=[(b"content-type", b"application/json")]),
        _noop_receive,
    )
    assert req.content_type == "application/json"


def test_content_type_none():
    req = Request(_make_scope(), _noop_receive)
    assert req.content_type is None


def test_cookies():
    req = Request(
        _make_scope(headers=[(b"cookie", b"a=1; b=2; c=3")]),
        _noop_receive,
    )
    cookies = req.cookies
    assert cookies == {"a": "1", "b": "2", "c": "3"}
    # Cached
    assert req.cookies is cookies


def test_cookies_empty():
    req = Request(_make_scope(), _noop_receive)
    assert req.cookies == {}


def test_parse_cookies_edge_cases():
    assert _parse_cookies("") == {}
    assert _parse_cookies("foo=bar") == {"foo": "bar"}
    assert _parse_cookies("a=1; b=2") == {"a": "1", "b": "2"}
    assert _parse_cookies("no-equal-sign") == {}


async def test_body():
    body = b'{"key": "value"}'

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    req = Request(_make_scope(), receive)
    result = await req.body()
    assert result == body
    # Cached
    assert await req.body() is result


async def test_json():
    body = b'{"key": "value"}'

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    req = Request(_make_scope(), receive)
    result = await req.json()
    assert result == {"key": "value"}
    # Cached
    assert await req.json() is result


async def test_form_urlencoded():
    body = b"name=Alice&age=30"

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    req = Request(
        _make_scope(
            method="POST",
            headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        ),
        receive,
    )
    form = await req.form()
    assert form.get("name") == "Alice"
    assert form.get("age") == "30"


async def test_form_multipart():
    boundary = "----boundary"
    body = (
        b"------boundary\r\n"
        b'Content-Disposition: form-data; name="field"\r\n\r\n'
        b"value\r\n"
        b"------boundary--\r\n"
    )

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    req = Request(
        _make_scope(
            method="POST",
            headers=[(b"content-type", f"multipart/form-data; boundary={boundary}".encode())],
        ),
        receive,
    )
    form = await req.form()
    assert form.get("field") == "value"


def test_path_params():
    req = Request(_make_scope(), _noop_receive, path_params={"id": 42})
    assert req.path_params == {"id": 42}


def test_path_params_default():
    req = Request(_make_scope(), _noop_receive)
    assert req.path_params == {}


def test_headers_cached():
    req = Request(_make_scope(headers=[(b"x-test", b"val")]), _noop_receive)
    h1 = req.headers
    h2 = req.headers
    assert h1 is h2


def test_query_params_cached():
    req = Request(_make_scope(query_string=b"a=1"), _noop_receive)
    q1 = req.query_params
    q2 = req.query_params
    assert q1 is q2
