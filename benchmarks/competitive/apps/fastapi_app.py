"""FastAPI app for competitive benchmarks.

Identical endpoint surface as benchmarks/competitive/apps/hawkapi_app.py.

Run: granian --interface asgi benchmarks.competitive.apps.fastapi_app:app
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


class Item(BaseModel):
    name: str
    price: float
    description: str = ""


@app.get("/json")
async def json_endpoint() -> dict[str, str]:
    return {"message": "Hello, World!"}


@app.get("/plaintext", response_class=PlainTextResponse)
async def plaintext_endpoint() -> str:
    return "Hello, World!"


@app.get("/users/{user_id}")
async def path_param_endpoint(user_id: int) -> dict[str, int]:
    return {"id": user_id}


@app.post("/items")
async def body_validation_endpoint(body: Item) -> dict[str, str | float]:
    return {"name": body.name, "price": body.price}


@app.get("/search")
async def query_params_endpoint(q: str = "", limit: int = 10) -> dict[str, str | int]:
    return {"query": q, "limit": limit}


for i in range(100):

    def make_handler(idx: int):
        async def handler() -> dict[str, int]:
            return {"id": idx}

        handler.__name__ = f"route_{idx}"
        return handler

    app.add_api_route(f"/route/{i}", make_handler(i), methods=["GET"])
