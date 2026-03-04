"""HawkAPI benchmark application."""

import msgspec

from hawkapi import HawkAPI

app = HawkAPI(openapi_url=None)


class Item(msgspec.Struct):
    id: int
    name: str
    price: float


ITEMS = [Item(id=i, name=f"item-{i}", price=i * 1.99) for i in range(1000)]


@app.get("/json")
async def json_hello():
    return {"message": "Hello, World!"}


@app.get("/users/{user_id:int}")
async def get_user(user_id: int):
    return {"id": user_id, "name": "Alice"}


@app.post("/items")
async def create_item(body: Item):
    return {"id": body.id, "name": body.name, "price": body.price}


@app.get("/items")
async def list_items():
    return ITEMS
