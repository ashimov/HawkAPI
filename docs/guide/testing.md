# Testing

HawkAPI provides a `TestClient` for easy testing without running a server.

## TestClient

```python
from hawkapi import HawkAPI
from hawkapi.testing import TestClient

app = HawkAPI()

@app.get("/hello")
async def hello():
    return {"message": "Hello!"}

def test_hello():
    client = TestClient(app)
    resp = client.get("/hello")
    assert resp.status_code == 200
    assert resp.json() == {"message": "Hello!"}
```

## HTTP Methods

```python
client = TestClient(app)

client.get("/items")
client.post("/items", json={"name": "Widget"})
client.put("/items/1", json={"name": "Updated"})
client.patch("/items/1", json={"price": 9.99})
client.delete("/items/1")
```

## Headers and Query Params

```python
resp = client.get(
    "/secure",
    headers={"Authorization": "Bearer token123"},
)

resp = client.get("/search", params={"q": "python"})
```

## Overriding Dependencies

```python
from hawkapi.testing import override

async def mock_db():
    yield FakeDB()

with override(app, {get_db: mock_db}):
    client = TestClient(app)
    resp = client.get("/users")
    assert resp.status_code == 200
```

## Cookie Jar

`TestClient` automatically persists cookies across requests. When a response contains `Set-Cookie` headers, the cookies are stored in `client.cookies` and sent with subsequent requests.

```python
client = TestClient(app)

# First request sets a session cookie via Set-Cookie header
client.post("/login", json={"user": "alice"})

# Cookie is automatically included in the next request
resp = client.get("/me")
assert resp.status_code == 200
```

You can also set cookies manually before making a request:

```python
client = TestClient(app)
client.cookies["session"] = "abc123"
resp = client.get("/dashboard")
```

## Response Cookies

Access cookies set by a single response via the `response.cookies` property. This parses the `Set-Cookie` headers into a `name -> value` dictionary.

```python
resp = client.post("/login", json={"user": "alice"})
assert "session" in resp.cookies
token = resp.cookies["session"]
```

## Case-Insensitive Headers

Response headers are returned as a `CaseInsensitiveDict`, so lookups work regardless of case:

```python
resp = client.get("/hello")
assert resp.headers["content-type"] == "application/json"
assert resp.headers["Content-Type"] == "application/json"
assert "CONTENT-TYPE" in resp.headers
```

## Assertion Helpers

`TestResponse` provides convenience properties for common assertions:

```python
resp = client.get("/hello")

# Status code checks
assert resp.is_success       # True for 2xx
assert not resp.is_redirect  # True for 3xx

# Raise on error status codes (4xx / 5xx)
resp.raise_for_status()  # raises HTTPStatusError if status >= 400
```

`raise_for_status()` throws an `HTTPStatusError` with `status_code` and `response` attributes:

```python
from hawkapi.testing.client import HTTPStatusError

resp = client.get("/not-found")
try:
    resp.raise_for_status()
except HTTPStatusError as exc:
    print(exc.status_code)  # 404
```

## Running Tests

```bash
pytest tests/ -x -q
pytest tests/ --cov=hawkapi -q   # with coverage
```
