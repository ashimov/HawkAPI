"""Benchmark: radix tree routing performance.

Compare HawkAPI's radix tree to linear route matching.
"""

import time

from hawkapi.routing._radix_tree import RadixTree
from hawkapi.routing.route import Route


def _make_handler():
    async def handler():
        pass
    return handler


def bench_routing():
    tree = RadixTree()

    # Register realistic routes (REST API pattern)
    prefixes = ["users", "posts", "comments", "tags", "categories", "products", "orders", "payments"]
    routes_registered = 0

    for prefix in prefixes:
        tree.insert(Route(
            path=f"/{prefix}",
            handler=_make_handler(),
            methods=frozenset({"GET", "HEAD"}),
            name=f"list_{prefix}",
        ))
        tree.insert(Route(
            path=f"/{prefix}",
            handler=_make_handler(),
            methods=frozenset({"POST"}),
            name=f"create_{prefix}",
        ))
        tree.insert(Route(
            path=f"/{prefix}/{{id:int}}",
            handler=_make_handler(),
            methods=frozenset({"GET", "HEAD"}),
            name=f"get_{prefix}",
        ))
        tree.insert(Route(
            path=f"/{prefix}/{{id:int}}",
            handler=_make_handler(),
            methods=frozenset({"PUT"}),
            name=f"update_{prefix}",
        ))
        tree.insert(Route(
            path=f"/{prefix}/{{id:int}}",
            handler=_make_handler(),
            methods=frozenset({"DELETE"}),
            name=f"delete_{prefix}",
        ))
        routes_registered += 5

    # Also add some nested routes
    for prefix in prefixes[:4]:
        tree.insert(Route(
            path=f"/{prefix}/{{id:int}}/comments",
            handler=_make_handler(),
            methods=frozenset({"GET", "HEAD"}),
            name=f"{prefix}_comments",
        ))
        tree.insert(Route(
            path=f"/{prefix}/{{id:int}}/comments/{{comment_id:int}}",
            handler=_make_handler(),
            methods=frozenset({"GET", "HEAD"}),
            name=f"{prefix}_comment_detail",
        ))
        routes_registered += 2

    print(f"Registered {routes_registered} routes across {len(prefixes)} resources\n")

    # Benchmark lookups
    test_paths = [
        ("/users", "GET"),
        ("/users/42", "GET"),
        ("/users/42", "PUT"),
        ("/products", "POST"),
        ("/products/99", "DELETE"),
        ("/users/1/comments", "GET"),
        ("/users/1/comments/5", "GET"),
        ("/nonexistent", "GET"),  # 404
    ]

    iterations = 100_000

    # Warmup
    for path, method in test_paths:
        tree.lookup(path, method)

    # Benchmark
    start = time.perf_counter()
    for _ in range(iterations):
        for path, method in test_paths:
            tree.lookup(path, method)
    elapsed = time.perf_counter() - start

    total_lookups = iterations * len(test_paths)
    per_lookup_ns = (elapsed / total_lookups) * 1_000_000_000

    print(f"Total lookups:    {total_lookups:,}")
    print(f"Total time:       {elapsed:.3f}s")
    print(f"Per lookup:       {per_lookup_ns:.0f} ns")
    print(f"Lookups/sec:      {total_lookups / elapsed:,.0f}")
    print()

    # Per-path breakdown
    print("Per-path breakdown:")
    for path, method in test_paths:
        start = time.perf_counter()
        for _ in range(iterations):
            tree.lookup(path, method)
        elapsed = time.perf_counter() - start
        ns = (elapsed / iterations) * 1_000_000_000
        result = tree.lookup(path, method)
        status = "found" if result else "404"
        print(f"  {method:6} {path:40} → {ns:6.0f} ns  ({status})")


if __name__ == "__main__":
    bench_routing()
