"""Litestar app for competitive benchmarks.

Identical endpoint surface as benchmarks/competitive/apps/hawkapi_app.py.

Run: granian --interface asgi benchmarks.competitive.apps.litestar_app:app
"""

from __future__ import annotations

import msgspec
from litestar import Litestar, MediaType, get, post


class Item(msgspec.Struct):
    name: str
    price: float
    description: str = ""


@get("/json")
async def json_endpoint() -> dict[str, str]:
    return {"message": "Hello, World!"}


@get("/plaintext", media_type=MediaType.TEXT)
async def plaintext_endpoint() -> str:
    return "Hello, World!"


@get("/users/{user_id:int}")
async def path_param_endpoint(user_id: int) -> dict[str, int]:
    return {"id": user_id}


@post("/items")
async def body_validation_endpoint(data: Item) -> dict[str, str | float]:
    return {"name": data.name, "price": data.price}


@get("/search")
async def query_params_endpoint(q: str = "", limit: int = 10) -> dict[str, str | int]:
    return {"query": q, "limit": limit}


def _make_route_handler(idx: int):
    @get(f"/route/{idx}", name=f"route_{idx}")
    async def handler() -> dict[str, int]:
        return {"id": idx}

    return handler


_dummy_routes = [_make_route_handler(i) for i in range(100)]

app = Litestar(
    route_handlers=[
        json_endpoint,
        plaintext_endpoint,
        path_param_endpoint,
        body_validation_endpoint,
        query_params_endpoint,
        *_dummy_routes,
    ],
    openapi_config=None,
)
