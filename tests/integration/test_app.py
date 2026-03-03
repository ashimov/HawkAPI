"""Integration tests for the full HawkAPI application."""

import msgspec
import pytest

from hawkapi import HawkAPI, Request, Response


async def _call_app(
    app: HawkAPI,
    method: str,
    path: str,
    body: bytes = b"",
    headers: list | None = None,
):
    """Helper to call an ASGI app and capture the response."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
    }

    if b"?" in path.encode():
        parts = path.split("?", 1)
        scope["path"] = parts[0]
        scope["query_string"] = parts[1].encode()

    sent_messages = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent_messages.append(message)

    await app(scope, receive, send)

    response_start = sent_messages[0]
    response_body = sent_messages[1] if len(sent_messages) > 1 else {"body": b""}

    return {
        "status": response_start["status"],
        "headers": dict(response_start.get("headers", [])),
        "body": response_body.get("body", b""),
    }


class TestBasicRouting:
    @pytest.mark.asyncio
    async def test_hello_world(self):
        app = HawkAPI()

        @app.get("/")
        async def hello():
            return {"message": "Hello, World!"}

        resp = await _call_app(app, "GET", "/")
        assert resp["status"] == 200
        data = msgspec.json.decode(resp["body"])
        assert data == {"message": "Hello, World!"}

    @pytest.mark.asyncio
    async def test_path_parameter(self):
        app = HawkAPI()

        @app.get("/users/{user_id:int}")
        async def get_user(user_id: int):
            return {"id": user_id, "name": f"User {user_id}"}

        resp = await _call_app(app, "GET", "/users/42")
        assert resp["status"] == 200
        data = msgspec.json.decode(resp["body"])
        assert data == {"id": 42, "name": "User 42"}

    @pytest.mark.asyncio
    async def test_multiple_path_params(self):
        app = HawkAPI()

        @app.get("/users/{user_id:int}/posts/{post_id:int}")
        async def get_post(user_id: int, post_id: int):
            return {"user_id": user_id, "post_id": post_id}

        resp = await _call_app(app, "GET", "/users/1/posts/99")
        assert resp["status"] == 200
        data = msgspec.json.decode(resp["body"])
        assert data == {"user_id": 1, "post_id": 99}

    @pytest.mark.asyncio
    async def test_404_not_found(self):
        app = HawkAPI()

        @app.get("/users")
        async def list_users():
            return []

        resp = await _call_app(app, "GET", "/nonexistent")
        assert resp["status"] == 404
        data = msgspec.json.decode(resp["body"])
        assert data["status"] == 404

    @pytest.mark.asyncio
    async def test_405_method_not_allowed(self):
        app = HawkAPI()

        @app.get("/users")
        async def list_users():
            return []

        resp = await _call_app(app, "DELETE", "/users")
        assert resp["status"] == 405
        assert b"allow" in dict(resp["headers"]) or any(
            k == b"allow" for k, v in resp["headers"].items()
        )


class TestHTTPMethods:
    @pytest.mark.asyncio
    async def test_post(self):
        app = HawkAPI()

        @app.post("/items")
        async def create_item(request: Request):
            data = await request.json()
            return {"created": data["name"]}

        body = msgspec.json.encode({"name": "Widget"})
        resp = await _call_app(app, "POST", "/items", body=body)
        assert resp["status"] == 201
        data = msgspec.json.decode(resp["body"])
        assert data == {"created": "Widget"}

    @pytest.mark.asyncio
    async def test_put(self):
        app = HawkAPI()

        @app.put("/items/{item_id:int}")
        async def update_item(item_id: int, request: Request):
            data = await request.json()
            return {"id": item_id, "name": data["name"]}

        body = msgspec.json.encode({"name": "Updated"})
        resp = await _call_app(app, "PUT", "/items/1", body=body)
        assert resp["status"] == 200

    @pytest.mark.asyncio
    async def test_delete(self):
        app = HawkAPI()

        @app.delete("/items/{item_id:int}")
        async def delete_item(item_id: int):
            return None

        resp = await _call_app(app, "DELETE", "/items/1")
        assert resp["status"] == 204

    @pytest.mark.asyncio
    async def test_patch(self):
        app = HawkAPI()

        @app.patch("/items/{item_id:int}")
        async def patch_item(item_id: int, request: Request):
            data = await request.json()
            return {"id": item_id, **data}

        body = msgspec.json.encode({"price": 19.99})
        resp = await _call_app(app, "PATCH", "/items/1", body=body)
        assert resp["status"] == 200


class TestBodyValidation:
    @pytest.mark.asyncio
    async def test_msgspec_struct_body(self):
        app = HawkAPI()

        class CreateUser(msgspec.Struct):
            name: str
            age: int

        @app.post("/users")
        async def create_user(body: CreateUser):
            return {"name": body.name, "age": body.age}

        body = msgspec.json.encode({"name": "Alice", "age": 30})
        resp = await _call_app(app, "POST", "/users", body=body)
        assert resp["status"] == 201
        data = msgspec.json.decode(resp["body"])
        assert data == {"name": "Alice", "age": 30}

    @pytest.mark.asyncio
    async def test_validation_error(self):
        app = HawkAPI()

        class CreateUser(msgspec.Struct):
            name: str
            age: int

        @app.post("/users")
        async def create_user(body: CreateUser):
            return {"name": body.name}

        # Invalid: age is string, not int
        body = b'{"name": "Alice", "age": "not a number"}'
        resp = await _call_app(app, "POST", "/users", body=body)
        assert resp["status"] == 400
        data = msgspec.json.decode(resp["body"])
        assert data["title"] == "Validation Error"
        assert data["status"] == 400

    @pytest.mark.asyncio
    async def test_struct_return_type(self):
        app = HawkAPI()

        class UserResponse(msgspec.Struct):
            id: int
            name: str

        @app.get("/users/{user_id:int}")
        async def get_user(user_id: int) -> UserResponse:
            return UserResponse(id=user_id, name="Alice")

        resp = await _call_app(app, "GET", "/users/1")
        assert resp["status"] == 200
        data = msgspec.json.decode(resp["body"])
        assert data == {"id": 1, "name": "Alice"}


class TestRouter:
    @pytest.mark.asyncio
    async def test_include_router(self):
        from hawkapi import Router

        app = HawkAPI()
        router = Router(prefix="/api/v1")

        @router.get("/items")
        async def list_items():
            return [{"id": 1}]

        app.include_router(router)

        resp = await _call_app(app, "GET", "/api/v1/items")
        assert resp["status"] == 200
        data = msgspec.json.decode(resp["body"])
        assert data == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_nested_router(self):
        from hawkapi import Router

        app = HawkAPI()
        api_router = Router(prefix="/api")
        v1_router = Router(prefix="/v1")

        @v1_router.get("/health")
        async def health():
            return {"status": "ok"}

        api_router.include_router(v1_router)
        app.include_router(api_router)

        resp = await _call_app(app, "GET", "/api/v1/health")
        assert resp["status"] == 200


class TestExceptionHandling:
    @pytest.mark.asyncio
    async def test_unhandled_exception_500(self):
        app = HawkAPI()

        @app.get("/error")
        async def fail():
            raise RuntimeError("Something went wrong")

        resp = await _call_app(app, "GET", "/error")
        assert resp["status"] == 500
        data = msgspec.json.decode(resp["body"])
        assert data["status"] == 500

    @pytest.mark.asyncio
    async def test_custom_exception_handler(self):
        app = HawkAPI()

        class NotFoundError(Exception):
            def __init__(self, resource: str):
                self.resource = resource

        @app.exception_handler(NotFoundError)
        async def handle_not_found(request: Request, exc: NotFoundError):
            return Response(
                content=msgspec.json.encode({"error": f"{exc.resource} not found"}),
                status_code=404,
                content_type="application/json",
            )

        @app.get("/users/{user_id:int}")
        async def get_user(user_id: int):
            raise NotFoundError("User")

        resp = await _call_app(app, "GET", "/users/1")
        assert resp["status"] == 404
        data = msgspec.json.decode(resp["body"])
        assert data == {"error": "User not found"}

    @pytest.mark.asyncio
    async def test_debug_mode_shows_detail(self):
        app = HawkAPI(debug=True)

        @app.get("/error")
        async def fail():
            raise ValueError("Detailed error info")

        resp = await _call_app(app, "GET", "/error")
        assert resp["status"] == 500
        data = msgspec.json.decode(resp["body"])
        assert "Detailed error info" in data["detail"]

    @pytest.mark.asyncio
    async def test_production_hides_detail(self):
        app = HawkAPI(debug=False)

        @app.get("/error")
        async def fail():
            raise ValueError("Secret error info")

        resp = await _call_app(app, "GET", "/error")
        assert resp["status"] == 500
        data = msgspec.json.decode(resp["body"])
        assert "Secret" not in data["detail"]


class TestHeadMethod:
    @pytest.mark.asyncio
    async def test_head_returns_no_body(self):
        app = HawkAPI()

        @app.get("/data")
        async def get_data():
            return {"key": "value"}

        resp = await _call_app(app, "HEAD", "/data")
        assert resp["status"] == 200
        assert resp["body"] == b""
