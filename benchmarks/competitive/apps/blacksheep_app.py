"""BlackSheep app for competitive benchmarks.

Identical endpoint surface as benchmarks/competitive/apps/hawkapi_app.py.

Run: granian --interface asgi benchmarks.competitive.apps.blacksheep_app:app
"""

from __future__ import annotations

from blacksheep import Application, FromJSON, Response, get, json, post, text
from blacksheep.contents import JSONContent

app = Application(show_error_details=False)


class Item:
    name: str
    price: float
    description: str

    def __init__(self, name: str = "", price: float = 0.0, description: str = "") -> None:
        self.name = name
        self.price = price
        self.description = description


@get("/json")
async def json_endpoint() -> Response:
    return json({"message": "Hello, World!"})


@get("/plaintext")
async def plaintext_endpoint() -> Response:
    return text("Hello, World!")


@get("/users/{user_id}")
async def path_param_endpoint(user_id: int) -> Response:
    return json({"id": user_id})


@post("/items")
async def body_validation_endpoint(body: FromJSON[Item]) -> Response:
    item = body.value
    return json({"name": item.name, "price": item.price})


@get("/search")
async def query_params_endpoint(q: str = "", limit: int = 10) -> Response:
    return json({"query": q, "limit": limit})


for i in range(100):

    def _make(idx: int):
        async def handler() -> Response:
            return Response(200, content=JSONContent({"id": idx}))

        handler.__name__ = f"route_{idx}"
        return handler

    app.router.add_get(f"/route/{i}", _make(i))
