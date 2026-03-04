"""Tests for the ``hawkapi new`` project scaffolding."""

from __future__ import annotations

import os
import tempfile

from hawkapi._scaffold.templates import generate_project


class TestScaffold:
    def test_generates_main_py(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject")
            assert os.path.isfile(os.path.join(d, "main.py"))

    def test_generates_pyproject_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject")
            content = open(os.path.join(d, "pyproject.toml")).read()  # noqa: SIM115
            assert "hawkapi" in content
            assert "myproject" in content

    def test_generates_dockerfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject", docker=True)
            assert os.path.isfile(os.path.join(d, "Dockerfile"))

    def test_no_dockerfile_when_not_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject", docker=False)
            assert not os.path.isfile(os.path.join(d, "Dockerfile"))
