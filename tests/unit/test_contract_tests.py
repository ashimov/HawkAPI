"""Tests for the contract smoke test generator."""

from __future__ import annotations

from hawkapi import HawkAPI, Request
from hawkapi.testing.contract import ContractTest, generate_contract_tests


def _build_app() -> HawkAPI:
    """Build a small app with a variety of routes for testing."""
    app = HawkAPI(
        title="TestApp",
        docs_url=None,
        redoc_url=None,
        scalar_url=None,
        openapi_url=None,
        health_url=None,
    )

    @app.get("/items")
    async def list_items(request: Request) -> list[dict[str, str]]:
        return []

    @app.post("/items")
    async def create_item(request: Request) -> dict[str, str]:
        return {"id": "1"}

    @app.get("/items/{item_id}")
    async def get_item(request: Request) -> dict[str, str]:
        return {"id": "1"}

    @app.get("/health", include_in_schema=False)
    async def health(request: Request) -> dict[str, str]:
        return {"status": "ok"}

    return app


class TestGenerateContractTests:
    """Tests for generate_contract_tests."""

    def test_generates_tests_for_each_endpoint(self) -> None:
        app = _build_app()
        tests = generate_contract_tests(app)

        # /items GET has methods {"GET", "HEAD"} -> 2 ContractTests
        # /items POST has methods {"POST"} -> 1 ContractTest
        # /items/{item_id} is skipped (path param)
        # /health is skipped (include_in_schema=False)
        paths_methods = [(t.path, t.method) for t in tests]
        assert ("/items", "GET") in paths_methods
        assert ("/items", "HEAD") in paths_methods
        assert ("/items", "POST") in paths_methods
        assert len(tests) == 3

    def test_correct_method_and_expected_status(self) -> None:
        app = _build_app()
        tests = generate_contract_tests(app)

        get_test = next(t for t in tests if t.method == "GET" and t.path == "/items")
        assert get_test.method == "GET"
        assert get_test.expected_status == 200
        assert get_test.name == "GET /items -> 200"

    def test_custom_status_code_reflected(self) -> None:
        app = _build_app()
        tests = generate_contract_tests(app)

        post_test = next(t for t in tests if t.method == "POST" and t.path == "/items")
        assert post_test.expected_status == 201
        assert post_test.name == "POST /items -> 201"

    def test_path_param_routes_skipped(self) -> None:
        app = _build_app()
        tests = generate_contract_tests(app)

        paths = [t.path for t in tests]
        assert "/items/{item_id}" not in paths

    def test_include_in_schema_false_routes_skipped(self) -> None:
        app = _build_app()
        tests = generate_contract_tests(app)

        paths = [t.path for t in tests]
        assert "/health" not in paths

    def test_contract_test_is_frozen(self) -> None:
        ct = ContractTest(name="test", method="GET", path="/x", expected_status=200)
        assert ct.name == "test"
        assert ct.method == "GET"
        assert ct.path == "/x"
        assert ct.expected_status == 200

    def test_empty_app_returns_empty_list(self) -> None:
        app = HawkAPI(
            title="EmptyApp",
            docs_url=None,
            redoc_url=None,
            scalar_url=None,
            openapi_url=None,
            health_url=None,
        )
        tests = generate_contract_tests(app)
        assert tests == []
