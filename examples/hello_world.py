"""HawkAPI — Hello World example.

Run with: uvicorn examples.hello_world:app
Or with:  granian --interface asgi examples.hello_world:app

Demonstrates: routing, validation, DI, middleware, WebSocket, controllers,
security, CSRF, sessions, per-route middleware, and streaming uploads.
"""

from typing import Annotated

import msgspec

from hawkapi import (
    Container,
    Controller,
    Depends,
    HawkAPI,
    HTMLResponse,
    Middleware,
    Query,
    RedirectResponse,
    Request,
    Response,
    Router,
    WebSocket,
    get,
    post,
)
from hawkapi.middleware.cors import CORSMiddleware
from hawkapi.middleware.csrf import CSRFMiddleware
from hawkapi.middleware.session import SessionMiddleware
from hawkapi.middleware.timing import TimingMiddleware

# --- Models ---


class CreateItem(msgspec.Struct):
    name: str
    price: Annotated[float, msgspec.Meta(ge=0)]
    description: str = ""


class ItemResponse(msgspec.Struct):
    id: int
    name: str
    price: float
    description: str


# --- In-memory store (simulating a database) ---


class ItemStore:
    def __init__(self):
        self._items: dict[int, ItemResponse] = {}
        self._next_id = 1

    def list(self, limit: int = 10, offset: int = 0) -> list[ItemResponse]:
        return list(self._items.values())[offset : offset + limit]

    def get(self, item_id: int) -> ItemResponse | None:
        return self._items.get(item_id)

    def create(self, body: CreateItem) -> ItemResponse:
        item = ItemResponse(
            id=self._next_id,
            name=body.name,
            price=body.price,
            description=body.description,
        )
        self._items[self._next_id] = item
        self._next_id += 1
        return item

    def delete(self, item_id: int) -> bool:
        return self._items.pop(item_id, None) is not None


# --- DI Container ---

container = Container()
container.singleton(ItemStore, factory=ItemStore)

# --- App ---

app = HawkAPI(
    title="HawkAPI Demo",
    version="1.0.0",
    description="Full-featured demo of HawkAPI framework",
    debug=True,
    container=container,
)

# --- Middleware ---

app.add_middleware(TimingMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# CSRF protection: requires a matching token in the X-CSRF-Token header (or
# form field) for unsafe methods (POST, PUT, DELETE, PATCH). A signed CSRF
# cookie is set automatically on safe requests (GET, HEAD, OPTIONS).
app.add_middleware(CSRFMiddleware, secret="change-me-to-a-real-secret-key")

# Session middleware: stores session data in a signed cookie. Access session
# data via request.scope["session"] inside route handlers.
app.add_middleware(
    SessionMiddleware,
    secret_key="another-secret-for-sessions",
    max_age=3600,  # 1 hour
)

# --- Lifecycle hooks ---


@app.on_startup
async def on_startup():
    print("🚀 HawkAPI started!")


@app.on_shutdown
async def on_shutdown():
    print("👋 HawkAPI shutting down...")


# --- Routes ---


@app.get("/")
async def root():
    return {"message": "Welcome to HawkAPI!", "docs": "/docs"}


@app.get("/items")
async def list_items(store: ItemStore, limit: int = 10, offset: int = 0):
    """List all items with pagination."""
    return store.list(limit, offset)


@app.get("/items/{item_id:int}")
async def get_item(item_id: int, store: ItemStore):
    """Get a single item by ID."""
    item = store.get(item_id)
    if item is None:
        return Response(
            content=msgspec.json.encode({"error": "Item not found"}),
            status_code=404,
            content_type="application/json",
        )
    return item


@app.post("/items")
async def create_item(body: CreateItem, store: ItemStore):
    """Create a new item."""
    return store.create(body)


@app.delete("/items/{item_id:int}")
async def delete_item(item_id: int, store: ItemStore):
    """Delete an item."""
    store.delete(item_id)
    return None


# --- Class-based controller ---


class HealthController(Controller):
    prefix = "/health"
    tags = ["health"]

    @get("/")
    async def check(self):
        """Health check endpoint."""
        return {"status": "healthy", "framework": "HawkAPI"}

    @get("/ready")
    async def ready(self):
        """Readiness probe."""
        return {"ready": True}


app.include_controller(HealthController)

# --- Sub-router ---

admin_router = Router(prefix="/admin", tags=["admin"])


@admin_router.get("/stats")
async def stats(store: ItemStore):
    return {"total_items": len(store.list(limit=9999))}


app.include_router(admin_router)


# --- WebSocket ---


@app.websocket("/ws")
async def websocket_echo(ws: WebSocket):
    """WebSocket echo server."""
    await ws.accept()
    async for message in ws:
        await ws.send_text(f"Echo: {message}")


# --- Custom exception handler ---


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return Response(
        content=msgspec.json.encode({"error": str(exc)}),
        status_code=400,
        content_type="application/json",
    )


# --- Session example ---


@app.get("/session")
async def read_session(request: Request):
    """Read session data. Visit /session/set?name=Alice first to populate it."""
    session: dict = request.scope.get("session", {})
    return {"session": session}


@app.get("/session/set")
async def write_session(request: Request, name: str = "World"):
    """Write to the session. The SessionMiddleware persists changes in a signed cookie."""
    session: dict = request.scope.get("session", {})
    session["name"] = name
    session["visits"] = session.get("visits", 0) + 1
    # Mutating the dict in scope is enough -- SessionMiddleware detects changes
    # and sets the updated cookie automatically.
    return {"message": f"Session updated for {name}", "session": session}


# --- Per-route middleware example ---
# Apply middleware only to specific routes instead of the whole app.
# Pass a list of middleware classes (or tuples of class + kwargs) to the
# decorator's `middleware` parameter.


@app.get("/timed", middleware=[TimingMiddleware])
async def timed_route():
    """This route has TimingMiddleware applied only to itself."""
    return {"message": "This response includes a Server-Timing header"}


@app.get(
    "/protected",
    middleware=[(CSRFMiddleware, {"secret": "per-route-secret"})],
)
async def protected_route():
    """This route has its own CSRF middleware with a separate secret."""
    return {"message": "CSRF-protected at the route level"}


# --- Streaming upload with request.stream() ---


@app.post("/upload")
async def streaming_upload(request: Request):
    """Accept a file upload and track progress using request.stream().

    Instead of buffering the entire body in memory, this reads chunks as they
    arrive from the client. Useful for large uploads.

    Example with curl:
        curl -X POST http://localhost:8000/upload \
             --data-binary @largefile.bin \
             -H "Content-Type: application/octet-stream"
    """
    total_bytes = 0
    chunk_count = 0

    async for chunk in request.stream():
        total_bytes += len(chunk)
        chunk_count += 1

    return {
        "message": "Upload complete",
        "total_bytes": total_bytes,
        "chunks_received": chunk_count,
    }
