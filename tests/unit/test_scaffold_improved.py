"""Tests for the improved ``hawkapi new`` scaffold templates."""

from __future__ import annotations

import os
import tempfile

from hawkapi._scaffold.templates import generate_project


class TestImprovedScaffold:
    def test_main_py_has_container_import(self) -> None:
        """Generated main.py should import Container for DI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject")
            content = open(os.path.join(d, "main.py")).read()  # noqa: SIM115
            assert "Container" in content

    def test_main_py_has_middleware_setup(self) -> None:
        """Generated main.py should configure CORS and RequestID middleware."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject")
            content = open(os.path.join(d, "main.py")).read()  # noqa: SIM115
            assert "CORSMiddleware" in content
            assert "RequestIDMiddleware" in content
            assert "add_middleware" in content

    def test_main_py_has_di_example(self) -> None:
        """Generated main.py should demonstrate dependency injection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject")
            content = open(os.path.join(d, "main.py")).read()  # noqa: SIM115
            assert "Depends" in content
            assert "container" in content
            assert "singleton" in content

    def test_generates_tests_directory(self) -> None:
        """Generated project should include a tests/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject")
            assert os.path.isdir(os.path.join(d, "tests"))

    def test_generates_test_main_py(self) -> None:
        """Generated project should include tests/test_main.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject")
            assert os.path.isfile(os.path.join(d, "tests", "test_main.py"))

    def test_test_main_py_has_test_client(self) -> None:
        """Generated test file should use TestClient."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject")
            content = open(os.path.join(d, "tests", "test_main.py")).read()  # noqa: SIM115
            assert "TestClient" in content

    def test_test_main_py_tests_health(self) -> None:
        """Generated test file should test the /health endpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject")
            content = open(os.path.join(d, "tests", "test_main.py")).read()  # noqa: SIM115
            assert "/health" in content

    def test_test_main_py_tests_greet(self) -> None:
        """Generated test file should test the /greet example route."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "myproject")
            generate_project(d, name="myproject")
            content = open(os.path.join(d, "tests", "test_main.py")).read()  # noqa: SIM115
            assert "/greet" in content

    def test_project_name_appears_in_main(self) -> None:
        """The project name should be substituted into the generated files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = os.path.join(tmpdir, "coolapi")
            generate_project(d, name="coolapi")
            content = open(os.path.join(d, "main.py")).read()  # noqa: SIM115
            assert 'title="coolapi"' in content
