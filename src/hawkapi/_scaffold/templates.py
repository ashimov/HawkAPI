"""Project scaffold templates for ``hawkapi new``."""

from __future__ import annotations

import os

MAIN_PY = '''\
"""Application entry point.

This file demonstrates key HawkAPI features:
- Dependency Injection (DI) with the Container
- Middleware setup (CORS, Request ID)
- Route handlers with injected dependencies
"""

from __future__ import annotations

from typing import Annotated

from hawkapi import Container, Depends, HawkAPI
from hawkapi.middleware.cors import CORSMiddleware
from hawkapi.middleware.request_id import RequestIDMiddleware

# ---------------------------------------------------------------------------
# 1. Dependency Injection — define services and register them in a Container
# ---------------------------------------------------------------------------


class GreetingService:
    """A sample service that generates greetings."""

    def __init__(self, default_name: str = "World") -> None:
        self.default_name = default_name

    def greet(self, name: str | None = None) -> str:
        return f"Hello, {{name or self.default_name}}!"


# Create a DI container and register the service as a singleton.
# Singletons are created once and reused for every request.
container = Container()
container.singleton(GreetingService, factory=lambda: GreetingService("{name}"))


# Dependency function — this is what route handlers declare as a parameter.
async def get_greeting_service() -> GreetingService:
    return await container.resolve(GreetingService)


# ---------------------------------------------------------------------------
# 2. Application & Middleware
# ---------------------------------------------------------------------------

app = HawkAPI(title="{name}", container=container)

# CORSMiddleware: allows cross-origin requests from any origin.
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# RequestIDMiddleware: assigns a unique ID to every request (useful for tracing).
app.add_middleware(RequestIDMiddleware)


# ---------------------------------------------------------------------------
# 3. Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    """Root endpoint — returns a welcome message."""
    return {{"message": "Welcome to {name}!"}}


@app.get("/health")
async def health():
    """Health-check endpoint."""
    return {{"status": "ok"}}


@app.get("/greet")
async def greet(
    name: str | None = None,
    svc: Annotated[GreetingService, Depends(get_greeting_service)] = None,  # noqa: B008
):
    """Example route that uses dependency injection.

    Query parameters:
        name (optional): The name to greet. Falls back to the service default.
    """
    return {{"greeting": svc.greet(name)}}
'''

TEST_MAIN_PY = '''\
"""Basic tests for the {name} application."""

from hawkapi.testing import TestClient

from main import app


client = TestClient(app)


class TestHealth:
    def test_health_returns_ok(self) -> None:
        """The /health endpoint should return status ok."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestGreet:
    def test_greet_default(self) -> None:
        """The /greet endpoint should return a greeting with the default name."""
        resp = client.get("/greet")
        assert resp.status_code == 200
        data = resp.json()
        assert "greeting" in data
        assert "{name}" in data["greeting"]

    def test_greet_with_name(self) -> None:
        """The /greet endpoint should use the provided name."""
        resp = client.get("/greet?name=Alice")
        assert resp.status_code == 200
        data = resp.json()
        assert "Alice" in data["greeting"]
'''

PYPROJECT_TOML = """\
[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["hawkapi>=0.1.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "ruff>=0.8"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
"""

DOCKERFILE = """\
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --frozen --no-dev
COPY . .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
"""

GITIGNORE = """\
__pycache__/
*.pyc
.venv/
dist/
.ruff_cache/
"""


def generate_project(project_dir: str, *, name: str, docker: bool = False) -> None:
    """Generate a new HawkAPI project in *project_dir*."""
    os.makedirs(project_dir, exist_ok=True)
    _write(project_dir, "main.py", MAIN_PY.format(name=name))
    _write(project_dir, "pyproject.toml", PYPROJECT_TOML.format(name=name))
    _write(project_dir, ".gitignore", GITIGNORE)
    if docker:
        _write(project_dir, "Dockerfile", DOCKERFILE)

    # Create tests directory and test file
    tests_dir = os.path.join(project_dir, "tests")
    os.makedirs(tests_dir, exist_ok=True)
    _write(tests_dir, "__init__.py", "")
    _write(tests_dir, "test_main.py", TEST_MAIN_PY.format(name=name))


def _write(base: str, filename: str, content: str) -> None:
    """Write *content* to *filename* inside *base* directory."""
    with open(os.path.join(base, filename), "w") as f:
        f.write(content)
