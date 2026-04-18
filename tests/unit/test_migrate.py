"""Tests for the FastAPI to HawkAPI codemod and the ``hawkapi migrate`` CLI."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from hawkapi._migrate.codemod import migrate_file
from hawkapi.cli import main as cli_main

# ---------------------------------------------------------------------------
# migrate_file: individual transforms
# ---------------------------------------------------------------------------


def test_import_fastapi_renamed():
    src = "from fastapi import FastAPI\n"
    new, warnings = migrate_file(src)
    assert new == "from hawkapi import HawkAPI\n"
    assert warnings == []


def test_import_apirouter_renamed():
    src = "from fastapi import APIRouter\n"
    new, _ = migrate_file(src)
    assert new == "from hawkapi import Router\n"


def test_import_multiple_symbols_renamed():
    src = "from fastapi import FastAPI, APIRouter, Depends, HTTPException\n"
    new, _ = migrate_file(src)
    assert new == "from hawkapi import HawkAPI, Router, Depends, HTTPException\n"


def test_import_responses_module():
    src = "from fastapi.responses import JSONResponse, HTMLResponse\n"
    new, _ = migrate_file(src)
    assert new == "from hawkapi.responses import JSONResponse, HTMLResponse\n"


def test_import_middleware_submodule():
    src = "from fastapi.middleware.cors import CORSMiddleware\n"
    new, _ = migrate_file(src)
    assert new == "from hawkapi.middleware import CORSMiddleware\n"


def test_import_testclient_to_testing():
    src = "from fastapi.testclient import TestClient\n"
    new, _ = migrate_file(src)
    assert new == "from hawkapi.testing import TestClient\n"


def test_bare_import_fastapi_module():
    src = "import fastapi\nx = fastapi.FastAPI()\n"
    new, _ = migrate_file(src)
    # ``import fastapi`` is rewritten to ``import hawkapi``. The attribute
    # access ``fastapi.FastAPI`` is intentionally NOT rewritten — see the
    # codemod docstring: bare-module attribute access is rare and the safer
    # default is to leave it for manual review.
    assert "import hawkapi" in new


def test_app_constructor_call_renamed():
    src = textwrap.dedent(
        """\
        from fastapi import FastAPI

        app = FastAPI(title="My API", version="1.0.0")
        """
    )
    new, _ = migrate_file(src)
    assert "app = HawkAPI(title=" in new
    assert "FastAPI" not in new


def test_apirouter_constructor_renamed():
    src = textwrap.dedent(
        """\
        from fastapi import APIRouter

        router = APIRouter(prefix="/v1")
        """
    )
    new, _ = migrate_file(src)
    assert "router = Router(prefix=" in new
    assert "APIRouter" not in new


def test_lifespan_startup():
    src = textwrap.dedent(
        """\
        from fastapi import FastAPI
        app = FastAPI()

        @app.on_event("startup")
        async def startup():
            pass
        """
    )
    new, _ = migrate_file(src)
    assert "@app.on_startup" in new
    assert "on_event" not in new


def test_lifespan_shutdown():
    src = textwrap.dedent(
        """\
        from fastapi import FastAPI
        app = FastAPI()

        @app.on_event("shutdown")
        async def shutdown():
            pass
        """
    )
    new, _ = migrate_file(src)
    assert "@app.on_shutdown" in new


def test_response_model_kwarg_left_alone():
    src = textwrap.dedent(
        """\
        from fastapi import FastAPI
        app = FastAPI()

        @app.get("/", response_model=Item)
        async def root():
            return {}
        """
    )
    new, _ = migrate_file(src)
    assert "response_model=Item" in new


def test_attribute_access_not_renamed():
    """``obj.FastAPI`` (attribute access) must NOT be renamed to ``obj.HawkAPI``."""
    src = "x = some.FastAPI\n"
    new, _ = migrate_file(src)
    assert new == "x = some.FastAPI\n"


# ---------------------------------------------------------------------------
# Pydantic -> msgspec (gated by convert_models)
# ---------------------------------------------------------------------------


def test_pydantic_not_converted_by_default():
    src = textwrap.dedent(
        """\
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
        """
    )
    new, _ = migrate_file(src)
    assert "BaseModel" in new
    assert "msgspec.Struct" not in new


def test_pydantic_converted_with_flag():
    src = textwrap.dedent(
        """\
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            qty: int
        """
    )
    new, _ = migrate_file(src, convert_models=True)
    assert "class Item(msgspec.Struct):" in new
    assert "import msgspec" in new


def test_pydantic_with_validator_skipped():
    src = textwrap.dedent(
        """\
        from pydantic import BaseModel, validator

        class Item(BaseModel):
            name: str

            @validator("name")
            def check_name(cls, v):
                return v
        """
    )
    new, warnings = migrate_file(src, convert_models=True)
    # Class body was NOT converted (kept BaseModel base).
    assert "class Item(BaseModel):" in new
    assert any("Item" in w and "validator" in w for w in warnings)


def test_msgspec_import_not_duplicated():
    src = textwrap.dedent(
        """\
        import msgspec
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
        """
    )
    new, _ = migrate_file(src, convert_models=True)
    assert new.count("import msgspec") == 1


# ---------------------------------------------------------------------------
# Path-parameter typing hints (warnings only)
# ---------------------------------------------------------------------------


def test_path_param_int_warning():
    src = textwrap.dedent(
        """\
        from fastapi import FastAPI
        app = FastAPI()

        @app.get("/users/{user_id}")
        async def get_user(user_id: int):
            return {}
        """
    )
    _new, warnings = migrate_file(src)
    assert any("{user_id:int}" in w for w in warnings)


def test_path_param_str_no_warning():
    src = textwrap.dedent(
        """\
        from fastapi import FastAPI
        app = FastAPI()

        @app.get("/users/{name}")
        async def get_user(name: str):
            return {}
        """
    )
    _new, warnings = migrate_file(src)
    assert not any("{name:" in w for w in warnings)


# ---------------------------------------------------------------------------
# Idempotency & robustness
# ---------------------------------------------------------------------------


def test_idempotent():
    src = textwrap.dedent(
        """\
        from fastapi import FastAPI, APIRouter

        app = FastAPI(title="x")
        router = APIRouter()

        @app.on_event("startup")
        async def startup():
            pass
        """
    )
    once, _ = migrate_file(src)
    twice, twice_warnings = migrate_file(once)
    assert once == twice
    assert twice_warnings == []


def test_unrelated_file_unchanged():
    src = textwrap.dedent(
        """\
        import os

        def hello():
            return os.getcwd()
        """
    )
    new, warnings = migrate_file(src)
    assert new == src
    assert warnings == []


def test_empty_source():
    new, warnings = migrate_file("")
    assert new == ""
    assert warnings == []


def test_syntax_error_preserved():
    src = "this is not python ::: ???\n"
    new, warnings = migrate_file(src)
    assert new == src
    assert warnings and "parse error" in warnings[0]


# ---------------------------------------------------------------------------
# Round-trip: a small FastAPI app is parseable after migration.
# ---------------------------------------------------------------------------


def test_roundtrip_parseable_and_uses_hawkapi():
    src = textwrap.dedent(
        """\
        from fastapi import FastAPI, APIRouter
        from fastapi.responses import JSONResponse

        app = FastAPI(title="Demo", version="0.1.0")
        router = APIRouter(prefix="/api")

        @router.get("/ping")
        async def ping():
            return JSONResponse({"ok": True})

        app.include_router(router)
        """
    )
    new, _ = migrate_file(src)

    # Module compiles.
    compile(new, "<migrated>", "exec")

    # Symbols look right.
    assert "from hawkapi import HawkAPI, Router" in new
    assert "from hawkapi.responses import JSONResponse" in new
    assert "app = HawkAPI(title=" in new
    assert "router = Router(prefix=" in new
    assert "FastAPI" not in new
    assert "APIRouter" not in new


# ---------------------------------------------------------------------------
# CLI: hawkapi migrate
# ---------------------------------------------------------------------------


def _write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_cli_migrate_in_place(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    proj = tmp_path / "app"
    _write(proj, "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    _write(proj, "subpkg/util.py", "from fastapi import APIRouter\nr = APIRouter()\n")
    # A non-Python file must be left alone.
    other = _write(proj, "README.txt", "untouched\n")

    cli_main(["migrate", str(proj)])

    main_py = (proj / "main.py").read_text()
    util_py = (proj / "subpkg" / "util.py").read_text()
    assert "from hawkapi import HawkAPI" in main_py
    assert "app = HawkAPI()" in main_py
    assert "from hawkapi import Router" in util_py
    assert other.read_text() == "untouched\n"

    out = capsys.readouterr().out
    assert "Migrated 2 files" in out


def test_cli_migrate_output_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    src_root = tmp_path / "src_app"
    out_root = tmp_path / "out_app"
    _write(src_root, "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")

    cli_main(["migrate", str(src_root), "--output", str(out_root)])

    # Original file untouched.
    assert "from fastapi import FastAPI" in (src_root / "main.py").read_text()
    # Output written.
    assert "from hawkapi import HawkAPI" in (out_root / "main.py").read_text()
    out = capsys.readouterr().out
    assert "Migrated 1 files" in out


def test_cli_migrate_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    proj = tmp_path / "app"
    p = _write(proj, "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    original = p.read_text()

    cli_main(["migrate", str(proj), "--dry-run"])

    captured = capsys.readouterr()
    # File unchanged on disk.
    assert p.read_text() == original
    # Diff printed.
    assert "-from fastapi import FastAPI" in captured.out
    assert "+from hawkapi import HawkAPI" in captured.out
    assert "(dry-run)" in captured.out


def test_cli_migrate_convert_models(tmp_path: Path):
    proj = tmp_path / "app"
    _write(
        proj,
        "models.py",
        textwrap.dedent(
            """\
            from pydantic import BaseModel

            class Item(BaseModel):
                name: str
            """
        ),
    )

    cli_main(["migrate", str(proj), "--convert-models"])

    body = (proj / "models.py").read_text()
    assert "class Item(msgspec.Struct):" in body
    assert "import msgspec" in body


def test_cli_migrate_idempotent_on_disk(tmp_path: Path):
    proj = tmp_path / "app"
    p = _write(
        proj,
        "main.py",
        textwrap.dedent(
            """\
            from fastapi import FastAPI

            app = FastAPI()

            @app.on_event("startup")
            async def startup():
                pass
            """
        ),
    )

    cli_main(["migrate", str(proj)])
    once = p.read_text()
    cli_main(["migrate", str(proj)])
    twice = p.read_text()
    assert once == twice


def test_cli_migrate_missing_path_exits(tmp_path: Path):
    missing = tmp_path / "does_not_exist"
    with pytest.raises(SystemExit) as exc:
        cli_main(["migrate", str(missing)])
    assert exc.value.code == 1


def test_cli_migrate_single_file(tmp_path: Path):
    fpath = tmp_path / "single.py"
    fpath.write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    cli_main(["migrate", str(fpath)])
    assert "from hawkapi import HawkAPI" in fpath.read_text()


def test_cli_migrate_skips_non_python(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    proj = tmp_path / "app"
    proj.mkdir()
    (proj / "notes.md").write_text("# nothing\n", encoding="utf-8")
    cli_main(["migrate", str(proj)])
    out = capsys.readouterr().out
    assert "No Python files found" in out


def test_cli_migrate_warnings_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    proj = tmp_path / "app"
    _write(
        proj,
        "main.py",
        textwrap.dedent(
            """\
            from fastapi import FastAPI
            app = FastAPI()

            @app.get("/users/{user_id}")
            async def get_user(user_id: int):
                return {}
            """
        ),
    )
    cli_main(["migrate", str(proj)])
    captured = capsys.readouterr()
    assert "{user_id:int}" in captured.err
    assert "1 warnings" in captured.out


def test_migrate_module_is_private():
    """The codemod ships under ``hawkapi._migrate`` (private) — assert it stays so."""
    import hawkapi._migrate as pkg

    assert os.path.basename(os.path.dirname(pkg.__file__ or "")) == "_migrate"
