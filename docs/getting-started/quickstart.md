# Quick Start

## Your First App

Create `app.py`:

```python
from hawkapi import HawkAPI

app = HawkAPI(title="My API", version="1.0.0")

@app.get("/")
async def root():
    return {"message": "Hello, World!"}

@app.get("/items/{item_id}")
async def get_item(item_id: int) -> dict:
    return {"item_id": item_id, "name": f"Item {item_id}"}

@app.post("/items", status_code=201)
async def create_item(name: str, price: float) -> dict:
    return {"name": name, "price": price}
```

## Run It

```bash
uvicorn app:app --reload
```

## Interactive Docs

Open your browser:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Scalar**: [http://localhost:8000/scalar](http://localhost:8000/scalar)
- **OpenAPI JSON**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

## Request Validation

HawkAPI validates path/query/body parameters automatically using `msgspec`:

```python
import msgspec

class Item(msgspec.Struct):
    name: str
    price: float
    quantity: int = 1

@app.post("/items", status_code=201)
async def create_item(item: Item) -> Item:
    return item
```

Invalid requests return an RFC 9457 Problem Details response:

```json
{
  "type": "https://hawkapi.ashimov.com/errors/validation",
  "title": "Validation Error",
  "status": 400,
  "detail": "1 validation error",
  "errors": [{"field": "price", "message": "Expected `float`, got `str`"}]
}
```

## Dependency Injection

```python
from hawkapi import Depends, HawkAPI

app = HawkAPI()

async def get_db():
    db = await connect()
    try:
        yield db
    finally:
        await db.close()

@app.get("/users")
async def list_users(db=Depends(get_db)):
    return await db.fetch_all("SELECT * FROM users")
```
