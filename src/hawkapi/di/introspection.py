"""DI container introspection utilities."""

from __future__ import annotations

from typing import Any


def container_graph(container: Any) -> dict[str, dict[str, Any]]:
    """Return a dict describing all registered providers."""
    graph: dict[str, dict[str, Any]] = {}
    for (service_type, name), provider in container._providers.items():
        key = service_type.__name__
        if name:
            key = f"{key}[{name}]"
        graph[key] = {
            "lifecycle": provider.lifecycle.value,
            "factory": repr(provider.factory),
            "name": name,
        }
    return graph


def to_mermaid(container: Any) -> str:
    """Generate a Mermaid diagram of the DI container."""
    graph = container_graph(container)
    lines: list[str] = ["graph TD"]
    for service, info in graph.items():
        lifecycle = info["lifecycle"]
        shape_open, shape_close = {
            "singleton": ("([", "])"),
            "scoped": ("[[", "]]"),
            "transient": ("((", "))"),
        }.get(lifecycle, ("[", "]"))
        lines.append(f"    {service}{shape_open}{service} ({lifecycle}){shape_close}")
    return "\n".join(lines)
