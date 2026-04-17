"""Sanic app for competitive benchmarks.

Identical endpoint surface as benchmarks/competitive/apps/hawkapi_app.py.

Run in ASGI mode with granian:
    granian --interface asgi benchmarks.competitive.apps.sanic_app:app
"""

from __future__ import annotations

import msgspec
from sanic import Request, Sanic, text
from sanic.response import JSONResponse, json


class Item(msgspec.Struct):
    name: str
    price: float
    description: str = ""


app = Sanic("bench")


@app.get("/json")
async def json_endpoint(request: Request) -> JSONResponse:
    return json({"message": "Hello, World!"})


@app.get("/plaintext")
async def plaintext_endpoint(request: Request):
    return text("Hello, World!")


@app.get("/users/<user_id:int>")
async def path_param_endpoint(request: Request, user_id: int) -> JSONResponse:
    return json({"id": user_id})


@app.post("/items")
async def body_validation_endpoint(request: Request) -> JSONResponse:
    body_bytes = request.body
    item = msgspec.json.decode(body_bytes, type=Item)
    return json({"name": item.name, "price": item.price})


@app.get("/search")
async def query_params_endpoint(request: Request) -> JSONResponse:
    q = request.args.get("q", "")
    limit = int(request.args.get("limit", "10"))
    return json({"query": q, "limit": limit})


for i in range(100):

    def _make(idx: int):
        async def handler(request: Request) -> JSONResponse:
            return json({"id": idx})

        handler.__name__ = f"route_{idx}"
        return handler

    app.add_route(_make(i), f"/route/{i}", methods=["GET"])
