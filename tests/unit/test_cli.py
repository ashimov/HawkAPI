"""Tests for CLI tool."""

from unittest.mock import MagicMock, patch

import pytest

from hawkapi.cli import main


def test_dev_calls_uvicorn():
    with patch("hawkapi.cli.uvicorn", create=True) as mock_uvicorn:
        mock_uvicorn.run = MagicMock()
        # Patch the import inside _run_dev
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            main(["dev", "myapp:app"])
        mock_uvicorn.run.assert_called_once_with(
            "myapp:app",
            host="127.0.0.1",
            port=8000,
            reload=True,
        )


def test_dev_custom_host_port():
    with patch("hawkapi.cli.uvicorn", create=True) as mock_uvicorn:
        mock_uvicorn.run = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            main(["dev", "myapp:app", "--host", "0.0.0.0", "--port", "3000"])
        mock_uvicorn.run.assert_called_once_with(
            "myapp:app",
            host="0.0.0.0",
            port=3000,
            reload=True,
        )


def test_dev_no_reload():
    with patch("hawkapi.cli.uvicorn", create=True) as mock_uvicorn:
        mock_uvicorn.run = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            main(["dev", "myapp:app", "--no-reload"])
        mock_uvicorn.run.assert_called_once_with(
            "myapp:app",
            host="127.0.0.1",
            port=8000,
            reload=False,
        )


def test_no_command_exits():
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 1


def test_missing_uvicorn_exits():
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _fake_import(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("No module named 'uvicorn'")
        return real_import(name, *args, **kwargs)

    with (
        patch.dict("sys.modules", {"uvicorn": None}),
        patch("builtins.__import__", side_effect=_fake_import),
        pytest.raises(SystemExit) as exc_info,
    ):
        main(["dev", "myapp:app"])
    assert exc_info.value.code == 1
