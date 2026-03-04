"""FastAPI benchmark application (for comparison).

Requires: pip install fastapi pydantic
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class Item(BaseModel):
    id: int
    name: str
    price: float


ITEMS = [Item(id=i, name=f"item-{i}", price=i * 1.99) for i in range(1000)]


@app.get("/json")
async def json_hello():
    return {"message": "Hello, World!"}


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id, "name": "Alice"}


@app.post("/items")
async def create_item(body: Item):
    return {"id": body.id, "name": body.name, "price": body.price}


@app.get("/items")
async def list_items():
    return [item.model_dump() for item in ITEMS]
