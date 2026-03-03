"""Radix tree (compressed trie) for O(path_length) route matching."""

from __future__ import annotations

import re
from collections.abc import Callable

from hawkapi.routing.param_converters import get_converter
from hawkapi.routing.route import Route

# Pattern to match {param} or {param:type} in path segments
_PARAM_PATTERN = re.compile(r"^\{(\w+)(?::(\w+))?\}$")


class RadixNode:
    """A node in the radix tree."""

    __slots__ = (
        "path",
        "children",
        "param_child",
        "wildcard_child",
        "handlers",
        "param_name",
        "param_converter",
    )

    def __init__(self, path: str = "") -> None:
        self.path: str = path
        self.children: dict[str, RadixNode] = {}
        self.param_child: RadixNode | None = None
        self.wildcard_child: RadixNode | None = None
        self.handlers: dict[str, Route] | None = None
        self.param_name: str | None = None
        self.param_converter: Callable[[str], object] | None = None


class LookupResult:
    """Result of a radix tree lookup."""

    __slots__ = ("route", "params")

    def __init__(self, route: Route, params: dict[str, object]) -> None:
        self.route = route
        self.params = params


class RadixTree:
    """Compressed trie for fast URL routing."""

    def __init__(self) -> None:
        self._root = RadixNode()
        self._routes: list[Route] = []

    @property
    def routes(self) -> list[Route]:
        return self._routes

    def insert(self, route: Route) -> None:
        """Insert a route into the radix tree."""
        path = route.path.strip("/")
        segments = path.split("/") if path else []
        node = self._root

        for segment in segments:
            param_match = _PARAM_PATTERN.match(segment)

            if param_match:
                # This is a parameter segment: {name} or {name:type}
                param_name = param_match.group(1)
                param_type = param_match.group(2) or "str"

                if node.param_child is None:
                    child = RadixNode()
                    child.param_name = param_name
                    child.param_converter = get_converter(param_type)
                    node.param_child = child
                node = node.param_child
            else:
                # Static segment
                if segment not in node.children:
                    node.children[segment] = RadixNode(segment)
                node = node.children[segment]

        # Register handlers for each method
        if node.handlers is None:
            node.handlers = {}

        for method in route.methods:
            if method in node.handlers:
                existing = node.handlers[method]
                raise ValueError(
                    f"Route conflict: {method} {route.path} conflicts with {method} {existing.path}"
                )
            node.handlers[method] = route

        self._routes.append(route)

    def lookup(self, path: str, method: str) -> LookupResult | None:
        """Look up a route by path and method. Returns None if not found."""
        path = path.strip("/")
        segments = path.split("/") if path else []
        params: dict[str, object] = {}

        result = self._lookup_recursive(self._root, segments, 0, method, params)
        return result

    def _lookup_recursive(
        self,
        node: RadixNode,
        segments: list[str],
        index: int,
        method: str,
        params: dict[str, object],
    ) -> LookupResult | None:
        """Recursively search the tree for a matching route."""
        if index == len(segments):
            # We've consumed all segments — check if this node has a handler
            if node.handlers and method in node.handlers:
                return LookupResult(node.handlers[method], params)
            return None

        segment = segments[index]

        # 1. Try static child first (most specific match)
        if segment in node.children:
            result = self._lookup_recursive(
                node.children[segment], segments, index + 1, method, params
            )
            if result is not None:
                return result

        # 2. Try parameter child
        if node.param_child is not None:
            param_node = node.param_child
            assert param_node.param_name is not None
            assert param_node.param_converter is not None
            try:
                converted = param_node.param_converter(segment)
            except (ValueError, TypeError):
                pass
            else:
                old_value = params.get(param_node.param_name)
                params[param_node.param_name] = converted
                result = self._lookup_recursive(param_node, segments, index + 1, method, params)
                if result is not None:
                    return result
                # Backtrack
                if old_value is None:
                    params.pop(param_node.param_name, None)
                else:
                    params[param_node.param_name] = old_value

        return None

    def find_allowed_methods(self, path: str) -> frozenset[str]:
        """Find all HTTP methods registered for a given path (for 405 responses)."""
        path = path.strip("/")
        segments = path.split("/") if path else []
        methods: set[str] = set()
        self._collect_methods(self._root, segments, 0, methods)
        return frozenset(methods)

    def _collect_methods(
        self,
        node: RadixNode,
        segments: list[str],
        index: int,
        methods: set[str],
    ) -> None:
        if index == len(segments):
            if node.handlers:
                methods.update(node.handlers.keys())
            return

        segment = segments[index]

        if segment in node.children:
            self._collect_methods(node.children[segment], segments, index + 1, methods)

        if node.param_child is not None:
            param_node = node.param_child
            assert param_node.param_converter is not None
            try:
                param_node.param_converter(segment)
            except (ValueError, TypeError):
                pass
            else:
                self._collect_methods(param_node, segments, index + 1, methods)
