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
        "handlers",
        "param_name",
        "param_converter",
    )

    def __init__(self, path: str = "") -> None:
        self.path: str = path
        self.children: dict[str, RadixNode] = {}
        self.param_child: RadixNode | None = None
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
                else:
                    existing_name = node.param_child.param_name
                    existing_converter = node.param_child.param_converter
                    new_converter = get_converter(param_type)
                    if existing_name != param_name or existing_converter is not new_converter:
                        raise ValueError(
                            f"Route conflict: parameter {{{param_name}:{param_type}}} "
                            f"conflicts with existing {{{existing_name}}} at the same position"
                        )
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
        """Look up a route by path and method. Returns None if not found.

        Iterative implementation with explicit backtrack stack to avoid
        recursive function call overhead.
        """
        # ASGI paths start with /; strip efficiently
        path_stripped = path[1:] if len(path) > 1 else ""
        if path_stripped.endswith("/"):
            path_stripped = path_stripped[:-1]
        segments = path_stripped.split("/") if path_stripped else []
        n = len(segments)
        params: dict[str, object] = {}

        # Each entry: (param_node_to_try, segment_index, params_snapshot)
        backtrack: list[tuple[RadixNode, int, dict[str, object]]] = []
        node = self._root
        idx = 0

        while True:
            # Advance through segments
            while idx < n:
                segment = segments[idx]

                # Try static child first (most specific)
                static_child = node.children.get(segment)
                if static_child is not None:
                    # Push param alternative if available for backtracking
                    if node.param_child is not None:
                        backtrack.append((node.param_child, idx, params.copy()))
                    node = static_child
                    idx += 1
                    continue

                # Try parameter child
                param_node = node.param_child
                if param_node is not None:
                    try:
                        converted = param_node.param_converter(segment)  # type: ignore[misc]
                    except (ValueError, TypeError):
                        break  # Dead end
                    params[param_node.param_name] = converted  # type: ignore[index]
                    node = param_node
                    idx += 1
                    continue

                break  # Dead end — no static or param child
            else:
                # All segments consumed — check for handler
                if node.handlers is not None and method in node.handlers:
                    return LookupResult(node.handlers[method], params)

            # Backtrack: try next saved param alternative
            found = False
            while backtrack:
                param_node, bt_idx, bt_params = backtrack.pop()
                segment = segments[bt_idx]
                try:
                    converted = param_node.param_converter(segment)  # type: ignore[misc]
                except (ValueError, TypeError):
                    continue
                params = bt_params
                params[param_node.param_name] = converted  # type: ignore[index]
                node = param_node
                idx = bt_idx + 1
                found = True
                break

            if not found:
                return None

    def find_allowed_methods(self, path: str) -> frozenset[str]:
        """Find all HTTP methods registered for a given path (for 405 responses)."""
        path_stripped = path[1:] if len(path) > 1 else ""
        if path_stripped.endswith("/"):
            path_stripped = path_stripped[:-1]
        segments = path_stripped.split("/") if path_stripped else []
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
            if param_node.param_converter is not None:
                try:
                    param_node.param_converter(segment)
                except (ValueError, TypeError):
                    pass
                else:
                    self._collect_methods(param_node, segments, index + 1, methods)
