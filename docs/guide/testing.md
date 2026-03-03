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

## Running Tests

```bash
pytest tests/ -x -q
pytest tests/ --cov=hawkapi -q   # with coverage
```
