# Routing

HawkAPI uses a radix-tree router for fast O(log n) path matching.

## Basic Routes

```python
from hawkapi import HawkAPI

app = HawkAPI()

@app.get("/users")
async def list_users():
    return [{"id": 1, "name": "Alice"}]

@app.post("/users", status_code=201)
async def create_user(name: str):
    return {"id": 2, "name": name}

@app.put("/users/{user_id}")
async def update_user(user_id: int, name: str):
    return {"id": user_id, "name": name}

@app.delete("/users/{user_id}")
async def delete_user(user_id: int):
    return None
```

## Path Parameters

Typed path parameters are supported with `{name:type}` syntax:

```python
@app.get("/items/{item_id:int}")
async def get_item(item_id: int):
    return {"item_id": item_id}

@app.get("/files/{path:path}")
async def get_file(path: str):
    return {"path": path}
```

## Sub-Routers

```python
from hawkapi import Router

api = Router(prefix="/api", tags=["api"])

@api.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(api)
# GET /api/health
```

## Class-Based Controllers

```python
from hawkapi import Controller, get, post

class UserController(Controller):
    prefix = "/users"
    tags = ["users"]

    @get("/")
    async def list_users(self):
        return []

    @post("/", status_code=201)
    async def create_user(self, name: str):
        return {"name": name}

app.include_controller(UserController)
```

## Per-Route Middleware

Apply middleware to specific routes by passing a `middleware` list to the route decorator. This is useful when only certain endpoints need authentication, CSRF protection, or other processing.

```python
from hawkapi.middleware.csrf import CSRFMiddleware
from hawkapi.middleware.rate_limit_redis import RedisRateLimitMiddleware

@app.post(
    "/payment",
    middleware=[
        (CSRFMiddleware, {"secret": "s3cret"}),
        (RedisRateLimitMiddleware, {"requests_per_second": 2.0}),
    ],
)
async def process_payment():
    return {"status": "ok"}
```

Each entry can be a middleware class (no extra arguments) or a `(MiddlewareClass, kwargs)` tuple. Per-route middleware runs inside the global middleware stack and only applies to the matched route.

## Mounting Sub-Applications

```python
from hawkapi import StaticFiles

app.mount("/static", StaticFiles(directory="static"))
```
