"""Tests for the `hawkapi init` CLI command."""

from __future__ import annotations

import os
from unittest.mock import patch

from hawkapi.cli import _ENV_CONTENT, _ENV_EXAMPLE_CONTENT, main


class TestInitCreatesFiles:
    """hawkapi init creates .env and .env.example."""

    def test_init_creates_env_files(self, tmp_path: object) -> None:
        """Running init creates .env and .env.example in the current directory."""
        with patch("hawkapi.cli.os.getcwd", return_value=str(tmp_path)):
            main(["init"])

        env_path = os.path.join(str(tmp_path), ".env")
        env_example_path = os.path.join(str(tmp_path), ".env.example")

        assert os.path.exists(env_path)
        assert os.path.exists(env_example_path)


class TestInitDoesNotOverwrite:
    """Running init twice does not overwrite existing files."""

    def test_init_skips_existing_files(self, tmp_path: object, capsys: object) -> None:
        """Running init twice skips files that already exist."""
        env_path = os.path.join(str(tmp_path), ".env")
        env_example_path = os.path.join(str(tmp_path), ".env.example")

        # Write custom content first
        with open(env_path, "w") as f:
            f.write("MY_CUSTOM=value\n")
        with open(env_example_path, "w") as f:
            f.write("MY_EXAMPLE=value\n")

        with patch("hawkapi.cli.os.getcwd", return_value=str(tmp_path)):
            main(["init"])

        # Original content should be preserved
        with open(env_path) as f:
            assert f.read() == "MY_CUSTOM=value\n"
        with open(env_example_path) as f:
            assert f.read() == "MY_EXAMPLE=value\n"

        captured = capsys.readouterr()
        assert "Already exists: .env" in captured.out
        assert "Already exists: .env.example" in captured.out


class TestInitCorrectContent:
    """Created files have correct content."""

    def test_env_file_has_commented_settings(self, tmp_path: object) -> None:
        """The .env file has commented-out settings."""
        with patch("hawkapi.cli.os.getcwd", return_value=str(tmp_path)):
            main(["init"])

        env_path = os.path.join(str(tmp_path), ".env")
        with open(env_path) as f:
            content = f.read()

        assert content == _ENV_CONTENT
        assert "# DEBUG=true" in content
        assert "# PORT=8000" in content
        assert "# DATABASE_URL=" in content
        assert "# SECRET_KEY=" in content

    def test_env_example_has_placeholder_values(self, tmp_path: object) -> None:
        """The .env.example file has placeholder (uncommented) values."""
        with patch("hawkapi.cli.os.getcwd", return_value=str(tmp_path)):
            main(["init"])

        env_example_path = os.path.join(str(tmp_path), ".env.example")
        with open(env_example_path) as f:
            content = f.read()

        assert content == _ENV_EXAMPLE_CONTENT
        assert "DEBUG=true" in content
        assert "PORT=8000" in content
        assert "DATABASE_URL=" in content
        assert "SECRET_KEY=" in content

    def test_init_prints_created_files(self, tmp_path: object, capsys: object) -> None:
        """Init prints what was created."""
        with patch("hawkapi.cli.os.getcwd", return_value=str(tmp_path)):
            main(["init"])

        captured = capsys.readouterr()
        assert "Created: .env" in captured.out
        assert "Created: .env.example" in captured.out
