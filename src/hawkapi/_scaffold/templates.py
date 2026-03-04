"""Project scaffold templates for ``hawkapi new``."""

from __future__ import annotations

import os

MAIN_PY = '''\
"""Application entry point."""

from hawkapi import HawkAPI

app = HawkAPI(title="{name}")


@app.get("/")
async def root():
    return {{"message": "Welcome to {name}!"}}


@app.get("/health")
async def health():
    return {{"status": "ok"}}
'''

PYPROJECT_TOML = '''\
[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["hawkapi>=0.1.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "ruff>=0.8"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
'''

DOCKERFILE = '''\
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --frozen --no-dev
COPY . .
EXPOSE 8000
CMD ["uv", "run", "hawkapi", "dev", "main:app", "--host", "0.0.0.0"]
'''

GITIGNORE = '''\
__pycache__/
*.pyc
.venv/
dist/
.ruff_cache/
'''


def generate_project(project_dir: str, *, name: str, docker: bool = False) -> None:
    """Generate a new HawkAPI project in *project_dir*."""
    os.makedirs(project_dir, exist_ok=True)
    _write(project_dir, "main.py", MAIN_PY.format(name=name))
    _write(project_dir, "pyproject.toml", PYPROJECT_TOML.format(name=name))
    _write(project_dir, ".gitignore", GITIGNORE)
    if docker:
        _write(project_dir, "Dockerfile", DOCKERFILE)


def _write(base: str, filename: str, content: str) -> None:
    """Write *content* to *filename* inside *base* directory."""
    with open(os.path.join(base, filename), "w") as f:
        f.write(content)
