"""Starlette app for competitive benchmarks.

Identical endpoint surface as benchmarks/competitive/apps/hawkapi_app.py.

Run: granian --interface asgi benchmarks.competitive.apps.starlette_app:app
"""

from __future__ import annotations

import msgspec
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route


class Item(msgspec.Struct):
    name: str
    price: float
    description: str = ""


async def json_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"message": "Hello, World!"})


async def plaintext_endpoint(request: Request) -> PlainTextResponse:
    return PlainTextResponse("Hello, World!")


async def path_param_endpoint(request: Request) -> JSONResponse:
    user_id = int(request.path_params["user_id"])
    return JSONResponse({"id": user_id})


async def body_validation_endpoint(request: Request) -> JSONResponse:
    body_bytes = await request.body()
    item = msgspec.json.decode(body_bytes, type=Item)
    return JSONResponse({"name": item.name, "price": item.price})


async def query_params_endpoint(request: Request) -> JSONResponse:
    q = request.query_params.get("q", "")
    limit = int(request.query_params.get("limit", "10"))
    return JSONResponse({"query": q, "limit": limit})


def _make_route_handler(idx: int):
    async def handler(request: Request) -> JSONResponse:
        return JSONResponse({"id": idx})

    handler.__name__ = f"route_{idx}"
    return handler


routes = [
    Route("/json", json_endpoint, methods=["GET"]),
    Route("/plaintext", plaintext_endpoint, methods=["GET"]),
    Route("/users/{user_id}", path_param_endpoint, methods=["GET"]),
    Route("/items", body_validation_endpoint, methods=["POST"]),
    Route("/search", query_params_endpoint, methods=["GET"]),
]

for i in range(100):
    routes.append(Route(f"/route/{i}", _make_route_handler(i), methods=["GET"]))

app = Starlette(routes=routes)
