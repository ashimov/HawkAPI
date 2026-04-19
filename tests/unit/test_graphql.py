"""Tests for the GraphQL thin-mount adapter."""

from __future__ import annotations

from typing import Any

import pytest

from hawkapi.app import HawkAPI
from hawkapi.testing import TestClient  # noqa: F401 — re-exported for type hints

# ---------------------------------------------------------------------------
# Stub executor — no graphql-core / strawberry required
# ---------------------------------------------------------------------------


async def stub_executor(
    query: str,
    variables: dict[str, Any] | None,
    operation_name: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    if "error" in query:
        return {"errors": [{"message": "stub error"}]}
    return {"data": {"query": query, "variables": variables or {}}}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app() -> HawkAPI:
    a = HawkAPI()
    a.mount_graphql("/graphql", executor=stub_executor)
    return a


@pytest.fixture()
def client(app: HawkAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST tests
# ---------------------------------------------------------------------------


def test_post_valid_returns_200(client: TestClient) -> None:
    resp = client.post("/graphql", json={"query": "{ hello }"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["query"] == "{ hello }"


def test_post_with_variables(client: TestClient) -> None:
    resp = client.post(
        "/graphql",
        json={"query": "{ hello }", "variables": {"name": "world"}},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["variables"] == {"name": "world"}


def test_post_missing_query_returns_400(client: TestClient) -> None:
    resp = client.post("/graphql", json={"variables": {}})
    assert resp.status_code == 400
    assert "errors" in resp.json()


def test_post_malformed_json_returns_400(client: TestClient) -> None:
    resp = client.post(
        "/graphql",
        body=b"not json",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400
    assert "errors" in resp.json()


# ---------------------------------------------------------------------------
# GET tests
# ---------------------------------------------------------------------------


def test_get_with_allow_get_true(client: TestClient) -> None:
    resp = client.get("/graphql?query={hello}")
    assert resp.status_code == 200
    assert "data" in resp.json()


def test_get_with_allow_get_false() -> None:
    a = HawkAPI()
    a.mount_graphql("/graphql", executor=stub_executor, allow_get=False)
    c = TestClient(a)
    resp = c.get("/graphql?query={hello}")
    assert resp.status_code == 405


def test_get_mutation_rejected() -> None:
    a = HawkAPI()
    a.mount_graphql("/graphql", executor=stub_executor, allow_get=True)
    c = TestClient(a)
    resp = c.get("/graphql?query=mutation{doThing}")
    assert resp.status_code == 400
    assert "errors" in resp.json()


# ---------------------------------------------------------------------------
# GraphiQL UI tests
# ---------------------------------------------------------------------------


def test_graphiql_true_serves_html() -> None:
    a = HawkAPI()
    a.mount_graphql("/graphql", executor=stub_executor, graphiql=True)
    c = TestClient(a)
    resp = c.get("/graphql", headers={"accept": "text/html,application/xhtml+xml"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_graphiql_false_returns_404() -> None:
    a = HawkAPI()
    a.mount_graphql("/graphql", executor=stub_executor, graphiql=False)
    c = TestClient(a)
    resp = c.get("/graphql", headers={"accept": "text/html,application/xhtml+xml"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Context injection tests
# ---------------------------------------------------------------------------


def test_context_factory_dict_merged() -> None:
    received: dict[str, Any] = {}

    async def exec_capture(
        query: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        received.update(context)
        return {"data": {}}

    def ctx_factory(request: Any) -> dict[str, Any]:
        return {"user_id": "u42"}

    a = HawkAPI()
    a.mount_graphql("/graphql", executor=exec_capture, context_factory=ctx_factory)
    c = TestClient(a)
    c.post("/graphql", json={"query": "{ hello }"})
    assert received.get("user_id") == "u42"


def test_context_factory_coroutine_awaited() -> None:
    received: dict[str, Any] = {}

    async def exec_capture(
        query: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        received.update(context)
        return {"data": {}}

    async def async_ctx_factory(request: Any) -> dict[str, Any]:
        return {"async_val": "yes"}

    a = HawkAPI()
    a.mount_graphql("/graphql", executor=exec_capture, context_factory=async_ctx_factory)
    c = TestClient(a)
    c.post("/graphql", json={"query": "{ hello }"})
    assert received.get("async_val") == "yes"


def test_context_request_is_request_object() -> None:
    from hawkapi.requests.request import Request

    received: list[Any] = []

    async def exec_capture(
        query: str,
        variables: dict[str, Any] | None,
        operation_name: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        received.append(context.get("request"))
        return {"data": {}}

    a = HawkAPI()
    a.mount_graphql("/graphql", executor=exec_capture)
    c = TestClient(a)
    c.post("/graphql", json={"query": "{ hello }"})
    assert len(received) == 1
    assert isinstance(received[0], Request)


# ---------------------------------------------------------------------------
# Adapter tests (require optional deps)
# ---------------------------------------------------------------------------


def test_from_graphql_core_end_to_end() -> None:
    pytest.importorskip("graphql")
    from graphql import GraphQLField, GraphQLObjectType, GraphQLSchema, GraphQLString

    from hawkapi.graphql.adapters import from_graphql_core

    schema = GraphQLSchema(
        query=GraphQLObjectType(
            "Query",
            {"hello": GraphQLField(GraphQLString, resolve=lambda obj, info: "world")},
        )
    )
    executor = from_graphql_core(schema)

    a = HawkAPI()
    a.mount_graphql("/graphql", executor=executor)
    c = TestClient(a)
    resp = c.post("/graphql", json={"query": "{ hello }"})
    assert resp.status_code == 200
    assert resp.json()["data"]["hello"] == "world"


def test_from_strawberry_end_to_end() -> None:
    pytest.importorskip("strawberry")
    import strawberry

    from hawkapi.graphql.adapters import from_strawberry

    @strawberry.type
    class Query:
        @strawberry.field
        def hello(self) -> str:
            return "world"

    schema = strawberry.Schema(query=Query)
    executor = from_strawberry(schema)

    a = HawkAPI()
    a.mount_graphql("/graphql", executor=executor)
    c = TestClient(a)
    resp = c.post("/graphql", json={"query": "{ hello }"})
    assert resp.status_code == 200
    assert resp.json()["data"]["hello"] == "world"


# ---------------------------------------------------------------------------
# Integration via TestClient
# ---------------------------------------------------------------------------


def test_integration_via_test_client(client: TestClient) -> None:
    resp = client.post("/graphql", json={"query": "{ ping }"})
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["data"]["query"] == "{ ping }"


def test_graphql_executor_protocol_is_importable() -> None:
    """GraphQLExecutor can be imported from hawkapi.graphql."""
    from hawkapi.graphql import GraphQLExecutor as GE

    assert GE is not None
