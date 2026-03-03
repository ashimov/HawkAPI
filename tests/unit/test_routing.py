"""Tests for the radix tree router."""

import pytest

from hawkapi.routing._radix_tree import RadixTree
from hawkapi.routing.route import Route


def _make_route(path: str, methods: set[str] | None = None) -> Route:
    async def dummy_handler():
        pass

    return Route(
        path=path,
        handler=dummy_handler,
        methods=frozenset(methods or {"GET"}),
        name=f"route_{path}",
    )


class TestRadixTree:
    def test_insert_and_lookup_root(self):
        tree = RadixTree()
        route = _make_route("/")
        tree.insert(route)

        result = tree.lookup("/", "GET")
        assert result is not None
        assert result.route is route
        assert result.params == {}

    def test_insert_and_lookup_static(self):
        tree = RadixTree()
        route = _make_route("/users")
        tree.insert(route)

        result = tree.lookup("/users", "GET")
        assert result is not None
        assert result.route is route

    def test_insert_and_lookup_nested_static(self):
        tree = RadixTree()
        route = _make_route("/api/v1/users")
        tree.insert(route)

        result = tree.lookup("/api/v1/users", "GET")
        assert result is not None
        assert result.route is route

    def test_lookup_not_found(self):
        tree = RadixTree()
        tree.insert(_make_route("/users"))

        result = tree.lookup("/posts", "GET")
        assert result is None

    def test_lookup_wrong_method(self):
        tree = RadixTree()
        tree.insert(_make_route("/users", {"GET"}))

        result = tree.lookup("/users", "POST")
        assert result is None

    def test_path_parameter_str(self):
        tree = RadixTree()
        route = _make_route("/users/{user_id}")
        tree.insert(route)

        result = tree.lookup("/users/42", "GET")
        assert result is not None
        assert result.params == {"user_id": "42"}

    def test_path_parameter_int(self):
        tree = RadixTree()
        route = _make_route("/users/{user_id:int}")
        tree.insert(route)

        result = tree.lookup("/users/42", "GET")
        assert result is not None
        assert result.params == {"user_id": 42}

    def test_path_parameter_int_rejects_non_int(self):
        tree = RadixTree()
        tree.insert(_make_route("/users/{user_id:int}"))

        result = tree.lookup("/users/abc", "GET")
        assert result is None

    def test_multiple_path_parameters(self):
        tree = RadixTree()
        route = _make_route("/users/{user_id:int}/posts/{post_id:int}")
        tree.insert(route)

        result = tree.lookup("/users/1/posts/42", "GET")
        assert result is not None
        assert result.params == {"user_id": 1, "post_id": 42}

    def test_static_priority_over_param(self):
        tree = RadixTree()
        static_route = _make_route("/users/me")
        param_route = _make_route("/users/{user_id}")
        tree.insert(static_route)
        tree.insert(param_route)

        # Static should match first
        result = tree.lookup("/users/me", "GET")
        assert result is not None
        assert result.route is static_route

        # Param should match others
        result = tree.lookup("/users/42", "GET")
        assert result is not None
        assert result.route is param_route
        assert result.params == {"user_id": "42"}

    def test_multiple_methods_same_path(self):
        tree = RadixTree()
        get_route = _make_route("/users", {"GET"})
        post_route = _make_route("/users", {"POST"})
        tree.insert(get_route)
        tree.insert(post_route)

        result_get = tree.lookup("/users", "GET")
        assert result_get is not None
        assert result_get.route is get_route

        result_post = tree.lookup("/users", "POST")
        assert result_post is not None
        assert result_post.route is post_route

    def test_route_conflict_raises(self):
        tree = RadixTree()
        tree.insert(_make_route("/users", {"GET"}))

        with pytest.raises(ValueError, match="Route conflict"):
            tree.insert(_make_route("/users", {"GET"}))

    def test_find_allowed_methods(self):
        tree = RadixTree()
        tree.insert(_make_route("/users", {"GET"}))
        tree.insert(_make_route("/users", {"POST"}))

        allowed = tree.find_allowed_methods("/users")
        assert allowed == frozenset({"GET", "POST"})

    def test_find_allowed_methods_empty(self):
        tree = RadixTree()
        allowed = tree.find_allowed_methods("/nonexistent")
        assert allowed == frozenset()

    def test_trailing_slash_handling(self):
        tree = RadixTree()
        route = _make_route("/users")
        tree.insert(route)

        result = tree.lookup("/users/", "GET")
        # Trailing slash on lookup, route registered without — should still match
        # because we strip trailing slashes
        assert result is not None

    def test_uuid_parameter(self):
        import uuid

        tree = RadixTree()
        route = _make_route("/items/{item_id:uuid}")
        tree.insert(route)

        test_uuid = "550e8400-e29b-41d4-a716-446655440000"
        result = tree.lookup(f"/items/{test_uuid}", "GET")
        assert result is not None
        assert result.params["item_id"] == uuid.UUID(test_uuid)

    def test_routes_property(self):
        tree = RadixTree()
        r1 = _make_route("/a")
        r2 = _make_route("/b")
        tree.insert(r1)
        tree.insert(r2)

        assert len(tree.routes) == 2
        assert r1 in tree.routes
        assert r2 in tree.routes
