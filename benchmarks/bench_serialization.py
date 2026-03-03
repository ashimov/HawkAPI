"""Benchmark: serialization performance (msgspec vs json stdlib)."""

import json
import time
import uuid
from datetime import datetime

import msgspec

from hawkapi.serialization.encoder import encode_response


class User(msgspec.Struct):
    id: int
    name: str
    email: str
    is_active: bool = True


class DetailedUser(msgspec.Struct):
    id: int
    name: str
    email: str
    created_at: str
    tags: list[str]
    metadata: dict[str, str]


def bench_serialization():
    # Small payload
    small_dict = {"id": 1, "name": "Alice", "email": "alice@example.com"}
    small_struct = User(id=1, name="Alice", email="alice@example.com")

    # Medium payload (list of structs)
    medium_list = [
        {"id": i, "name": f"User {i}", "email": f"user{i}@example.com", "is_active": i % 2 == 0}
        for i in range(100)
    ]
    medium_structs = [
        User(id=i, name=f"User {i}", email=f"user{i}@example.com", is_active=i % 2 == 0)
        for i in range(100)
    ]

    # Large payload
    large_list = [
        {
            "id": i,
            "name": f"User {i}",
            "email": f"user{i}@example.com",
            "created_at": "2024-01-01T00:00:00Z",
            "tags": ["admin", "active", f"group-{i % 10}"],
            "metadata": {"role": "admin", "department": f"dept-{i % 5}"},
        }
        for i in range(1000)
    ]

    iterations = 10_000

    print("=== Serialization Benchmark ===\n")

    # --- Small dict ---
    start = time.perf_counter()
    for _ in range(iterations):
        encode_response(small_dict)
    hawk_time = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(iterations):
        json.dumps(small_dict).encode("utf-8")
    stdlib_time = time.perf_counter() - start

    print(f"Small dict ({len(json.dumps(small_dict))} bytes):")
    print(f"  HawkAPI (msgspec): {hawk_time:.3f}s ({iterations / hawk_time:,.0f} ops/sec)")
    print(f"  stdlib json:       {stdlib_time:.3f}s ({iterations / stdlib_time:,.0f} ops/sec)")
    print(f"  Speedup:           {stdlib_time / hawk_time:.1f}x\n")

    # --- Small struct ---
    start = time.perf_counter()
    for _ in range(iterations):
        encode_response(small_struct)
    hawk_struct_time = time.perf_counter() - start

    print(f"Small Struct:")
    print(f"  HawkAPI (msgspec): {hawk_struct_time:.3f}s ({iterations / hawk_struct_time:,.0f} ops/sec)")
    print(f"  Speedup vs dict:   {hawk_time / hawk_struct_time:.1f}x\n")

    # --- Medium list (100 items) ---
    start = time.perf_counter()
    for _ in range(iterations):
        encode_response(medium_list)
    hawk_med = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(iterations):
        json.dumps(medium_list).encode("utf-8")
    stdlib_med = time.perf_counter() - start

    print(f"Medium list (100 items, {len(json.dumps(medium_list))} bytes):")
    print(f"  HawkAPI (msgspec): {hawk_med:.3f}s ({iterations / hawk_med:,.0f} ops/sec)")
    print(f"  stdlib json:       {stdlib_med:.3f}s ({iterations / stdlib_med:,.0f} ops/sec)")
    print(f"  Speedup:           {stdlib_med / hawk_med:.1f}x\n")

    # --- Large list (1000 items) ---
    iters_large = 1_000
    start = time.perf_counter()
    for _ in range(iters_large):
        encode_response(large_list)
    hawk_large = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(iters_large):
        json.dumps(large_list).encode("utf-8")
    stdlib_large = time.perf_counter() - start

    print(f"Large list (1000 items, {len(json.dumps(large_list))} bytes):")
    print(f"  HawkAPI (msgspec): {hawk_large:.3f}s ({iters_large / hawk_large:,.0f} ops/sec)")
    print(f"  stdlib json:       {stdlib_large:.3f}s ({iters_large / stdlib_large:,.0f} ops/sec)")
    print(f"  Speedup:           {stdlib_large / hawk_large:.1f}x\n")


if __name__ == "__main__":
    bench_serialization()
