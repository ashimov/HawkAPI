"""Performance and memory budget tests.

These tests are NOT collected by the default ``pytest tests/`` invocation
(``testpaths`` in ``pyproject.toml`` only includes ``tests/unit`` and
``tests/integration``). Run them explicitly:

    uv run pytest tests/perf/ -m memory --memray -v

They depend on ``pytest-memray`` which only supports Linux/macOS.
"""
