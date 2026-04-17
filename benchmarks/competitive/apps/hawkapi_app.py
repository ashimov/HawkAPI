"""HawkAPI app for competitive benchmarks.

Identical endpoint surface across all framework apps in benchmarks/competitive/apps/.

Run: granian --interface asgi benchmarks.competitive.apps.hawkapi_app:app
"""

from __future__ import annotations

import msgspec

from hawkapi import HawkAPI
from hawkapi.responses.plain_text import PlainTextResponse

app = HawkAPI(
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
    scalar_url=None,
    health_url=None,
    readyz_url=None,
    livez_url=None,
)


class Item(msgspec.Struct):
    name: str
    price: float
    description: str = ""


@app.get("/json")
async def json_endpoint() -> dict[str, str]:
    return {"message": "Hello, World!"}


@app.get("/plaintext")
async def plaintext_endpoint() -> PlainTextResponse:
    return PlainTextResponse("Hello, World!")


@app.get("/users/{user_id:int}")
async def path_param_endpoint(user_id: int) -> dict[str, int]:
    return {"id": user_id}


@app.post("/items")
async def body_validation_endpoint(body: Item) -> dict[str, str | float]:
    return {"name": body.name, "price": body.price}


@app.get("/search")
async def query_params_endpoint(q: str = "", limit: int = 10) -> dict[str, str | int]:
    return {"query": q, "limit": limit}


# 100 dummy routes for routing benchmark
for i in range(100):

    def make_handler(idx: int):
        async def handler() -> dict[str, int]:
            return {"id": idx}

        handler.__name__ = f"route_{idx}"
        return handler

    app.add_route(f"/route/{i}", make_handler(i), methods={"GET"})
