"""Tests for the feature-flags subsystem."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from hawkapi.flags import (
    EnvFlagProvider,
    EvalContext,
    FileFlagProvider,
    FlagDisabled,
    Flags,
    StaticFlagProvider,
    get_flags,
    requires_flag,
)

# ---------------------------------------------------------------------------
# StaticFlagProvider
# ---------------------------------------------------------------------------


async def test_static_bool_true() -> None:
    p = StaticFlagProvider({"feat": True})
    assert await p.get_bool("feat", False) is True


async def test_static_bool_false() -> None:
    p = StaticFlagProvider({"feat": False})
    assert await p.get_bool("feat", True) is False


async def test_static_bool_int_coercion() -> None:
    p = StaticFlagProvider({"feat": 1, "off": 0})
    assert await p.get_bool("feat", False) is True
    assert await p.get_bool("off", True) is False


async def test_static_bool_string_stays_default() -> None:
    p = StaticFlagProvider({"feat": "true"})
    assert await p.get_bool("feat", False) is False  # strings → default


async def test_static_bool_missing_returns_default() -> None:
    p = StaticFlagProvider({})
    assert await p.get_bool("missing", True) is True


async def test_static_string_happy() -> None:
    p = StaticFlagProvider({"color": "blue"})
    assert await p.get_string("color", "red") == "blue"


async def test_static_string_wrong_type_returns_default() -> None:
    p = StaticFlagProvider({"color": 42})
    assert await p.get_string("color", "red") == "red"


async def test_static_string_missing_returns_default() -> None:
    p = StaticFlagProvider({})
    assert await p.get_string("x", "fallback") == "fallback"


async def test_static_number_int() -> None:
    p = StaticFlagProvider({"rate": 5})
    assert await p.get_number("rate", 0.0) == 5.0


async def test_static_number_float() -> None:
    p = StaticFlagProvider({"rate": 1.5})
    assert await p.get_number("rate", 0.0) == 1.5


async def test_static_number_bool_stays_default() -> None:
    # bool is subclass of int but should NOT be coerced to a number
    p = StaticFlagProvider({"rate": True})
    assert await p.get_number("rate", 99.0) == 99.0


async def test_static_number_missing_returns_default() -> None:
    p = StaticFlagProvider({})
    assert await p.get_number("rate", 3.14) == 3.14


# ---------------------------------------------------------------------------
# EnvFlagProvider
# ---------------------------------------------------------------------------


async def test_env_bool_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    p = EnvFlagProvider()
    for val in ("1", "true", "True", "TRUE", "yes", "YES", "on", "ON"):
        monkeypatch.setenv("HAWKAPI_FLAG_MY_FEAT", val)
        assert await p.get_bool("my-feat", False) is True


async def test_env_bool_falsy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    p = EnvFlagProvider()
    for val in ("0", "false", "False", "FALSE", "no", "NO", "off", "OFF"):
        monkeypatch.setenv("HAWKAPI_FLAG_MY_FEAT", val)
        assert await p.get_bool("my-feat", True) is False


async def test_env_bool_unknown_value_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAWKAPI_FLAG_MY_FEAT", "maybe")
    p = EnvFlagProvider()
    assert await p.get_bool("my-feat", True) is True


async def test_env_bool_missing_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAWKAPI_FLAG_NONEXISTENT", raising=False)
    p = EnvFlagProvider()
    assert await p.get_bool("nonexistent", True) is True


async def test_env_key_normalisation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dots and dashes in key names are converted to underscores."""
    monkeypatch.setenv("HAWKAPI_FLAG_FOO_BAR_BAZ", "1")
    p = EnvFlagProvider()
    assert await p.get_bool("foo.bar-baz", False) is True


async def test_env_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAWKAPI_FLAG_COLOR", "green")
    p = EnvFlagProvider()
    assert await p.get_string("color", "red") == "green"


async def test_env_number(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAWKAPI_FLAG_RATE", "2.5")
    p = EnvFlagProvider()
    assert await p.get_number("rate", 0.0) == 2.5


async def test_env_number_invalid_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAWKAPI_FLAG_RATE", "not-a-number")
    p = EnvFlagProvider()
    assert await p.get_number("rate", 7.0) == 7.0


async def test_env_custom_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYAPP_FEAT", "1")
    p = EnvFlagProvider(prefix="MYAPP_")
    assert await p.get_bool("feat", False) is True


# ---------------------------------------------------------------------------
# FileFlagProvider — JSON
# ---------------------------------------------------------------------------


async def test_file_provider_json(tmp_path: Path) -> None:
    f = tmp_path / "flags.json"
    f.write_text(json.dumps({"my-flag": True, "rate": 1.5, "color": "red"}))
    p = FileFlagProvider(f)
    assert await p.get_bool("my-flag", False) is True
    assert await p.get_number("rate", 0.0) == 1.5
    assert await p.get_string("color", "") == "red"


async def test_file_provider_json_missing_key(tmp_path: Path) -> None:
    f = tmp_path / "flags.json"
    f.write_text(json.dumps({}))
    p = FileFlagProvider(f)
    assert await p.get_bool("absent", True) is True


async def test_file_provider_mtime_reload(tmp_path: Path) -> None:
    """Provider reloads when file mtime changes."""
    f = tmp_path / "flags.json"
    f.write_text(json.dumps({"feat": False}))
    p = FileFlagProvider(f)
    assert await p.get_bool("feat", True) is False

    # Write new content and bump mtime so the provider detects the change
    f.write_text(json.dumps({"feat": True}))
    new_mtime = f.stat().st_mtime + 1
    os.utime(f, (new_mtime, new_mtime))

    assert await p.get_bool("feat", False) is True


async def test_file_provider_toml(tmp_path: Path) -> None:
    f = tmp_path / "flags.toml"
    f.write_text('my-flag = true\nrate = 2.5\ncolor = "blue"\n')
    p = FileFlagProvider(f)
    assert await p.get_bool("my-flag", False) is True
    assert await p.get_number("rate", 0.0) == 2.5
    assert await p.get_string("color", "") == "blue"


async def test_file_provider_yaml(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    f = tmp_path / "flags.yaml"
    f.write_text("my-flag: true\nrate: 1.5\ncolor: purple\n")
    p = FileFlagProvider(f)
    assert await p.get_bool("my-flag", False) is True
    assert await p.get_number("rate", 0.0) == 1.5
    assert await p.get_string("color", "") == "purple"


async def test_file_provider_yml_extension(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    f = tmp_path / "flags.yml"
    f.write_text("feat: true\n")
    p = FileFlagProvider(f)
    assert await p.get_bool("feat", False) is True


async def test_file_provider_unknown_extension_raises(tmp_path: Path) -> None:
    f = tmp_path / "flags.ini"
    f.write_text("[section]\nfeat = true\n")
    p = FileFlagProvider(f)
    with pytest.raises(ValueError, match="Unsupported flag file extension"):
        await p.get_bool("feat", False)


async def test_file_provider_missing_file_returns_default(tmp_path: Path) -> None:
    f = tmp_path / "nonexistent.json"
    p = FileFlagProvider(f)
    assert await p.get_bool("feat", True) is True


# ---------------------------------------------------------------------------
# Flags facade
# ---------------------------------------------------------------------------


async def test_flags_bool() -> None:
    provider = StaticFlagProvider({"f": True})
    flags = Flags(provider)
    assert await flags.bool("f") is True


async def test_flags_string() -> None:
    provider = StaticFlagProvider({"f": "hello"})
    flags = Flags(provider)
    assert await flags.string("f") == "hello"


async def test_flags_number() -> None:
    provider = StaticFlagProvider({"f": 3.0})
    flags = Flags(provider)
    assert await flags.number("f") == 3.0


async def test_flags_require_passes_when_enabled() -> None:
    provider = StaticFlagProvider({"feat": True})
    flags = Flags(provider)
    await flags.require("feat")  # must not raise


async def test_flags_require_raises_flag_disabled() -> None:
    provider = StaticFlagProvider({"feat": False})
    flags = Flags(provider)
    with pytest.raises(FlagDisabled) as exc_info:
        await flags.require("feat")
    assert exc_info.value.key == "feat"
    assert "feat" in str(exc_info.value)


async def test_flags_require_missing_key_raises() -> None:
    provider = StaticFlagProvider({})
    flags = Flags(provider)
    with pytest.raises(FlagDisabled):
        await flags.require("absent")


async def test_flags_per_call_context_override() -> None:
    """Context passed at call-time overrides the instance context."""
    provider = StaticFlagProvider({"f": True})
    instance_ctx = EvalContext(user_id="alice")
    call_ctx = EvalContext(user_id="bob")
    flags = Flags(provider, instance_ctx)
    # StaticFlagProvider ignores context — just verify no error and correct value
    assert await flags.bool("f", context=call_ctx) is True


# ---------------------------------------------------------------------------
# Plugin hook dispatch
# ---------------------------------------------------------------------------


async def test_plugin_hook_called_on_evaluation() -> None:
    """on_flag_evaluated is fired after each get_bool call."""
    calls: list[tuple[Any, Any]] = []

    class _Plugin:
        def on_flag_evaluated(self, key: str, value: Any, context: Any) -> None:
            calls.append((key, value))

    class _FakeApp:
        _plugins = [_Plugin()]

    provider = StaticFlagProvider({"feat": True})
    flags = Flags(provider, app=_FakeApp())
    await flags.bool("feat")
    assert calls == [("feat", True)]


async def test_plugin_hook_exception_does_not_break_evaluation() -> None:
    """A crashing hook must NOT propagate out of Flags."""

    class _BadPlugin:
        def on_flag_evaluated(self, key: str, value: Any, context: Any) -> None:
            raise RuntimeError("boom")

    class _FakeApp:
        _plugins = [_BadPlugin()]

    provider = StaticFlagProvider({"feat": True})
    flags = Flags(provider, app=_FakeApp())
    result = await flags.bool("feat")
    assert result is True


# ---------------------------------------------------------------------------
# HawkAPI(flags=...) integration
# ---------------------------------------------------------------------------


def test_hawkapi_default_flags_is_static_provider() -> None:
    from hawkapi import HawkAPI
    from hawkapi.flags.providers import StaticFlagProvider as SP

    app = HawkAPI(openapi_url=None)
    assert isinstance(app.flags, SP)


def test_hawkapi_custom_flags_stored() -> None:
    from hawkapi import HawkAPI

    provider = StaticFlagProvider({"x": True})
    app = HawkAPI(openapi_url=None, flags=provider)
    assert app.flags is provider


# ---------------------------------------------------------------------------
# @requires_flag decorator
# ---------------------------------------------------------------------------


def _make_scope(hawk: Any) -> dict[str, Any]:
    return {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
        "app": hawk,
    }


async def _dummy_receive() -> dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


async def test_requires_flag_passes_when_on() -> None:
    from hawkapi import HawkAPI
    from hawkapi.requests.request import Request

    provider = StaticFlagProvider({"feat": True})
    hawk = HawkAPI(openapi_url=None, flags=provider)

    @requires_flag("feat")
    async def handler(request: Request) -> str:
        return "ok"

    req = Request(_make_scope(hawk), _dummy_receive)
    result = await handler(req)
    assert result == "ok"


async def test_requires_flag_raises_404_when_off() -> None:
    from hawkapi import HawkAPI
    from hawkapi.exceptions import HTTPException
    from hawkapi.requests.request import Request

    provider = StaticFlagProvider({"feat": False})
    hawk = HawkAPI(openapi_url=None, flags=provider)

    @requires_flag("feat")
    async def handler(request: Request) -> str:
        return "ok"

    req = Request(_make_scope(hawk), _dummy_receive)
    with pytest.raises(HTTPException) as exc_info:
        await handler(req)
    assert exc_info.value.status_code == 404


async def test_requires_flag_custom_status_code() -> None:
    from hawkapi import HawkAPI
    from hawkapi.exceptions import HTTPException
    from hawkapi.requests.request import Request

    provider = StaticFlagProvider({"feat": False})
    hawk = HawkAPI(openapi_url=None, flags=provider)

    @requires_flag("feat", status_code=403)
    async def handler(request: Request) -> str:
        return "ok"

    req = Request(_make_scope(hawk), _dummy_receive)
    with pytest.raises(HTTPException) as exc_info:
        await handler(req)
    assert exc_info.value.status_code == 403


async def test_requires_flag_no_request_raises_500() -> None:
    from hawkapi.exceptions import HTTPException

    @requires_flag("feat")
    async def handler_no_request() -> str:
        return "ok"

    with pytest.raises(HTTPException) as exc_info:
        await handler_no_request()
    assert exc_info.value.status_code == 500
    assert "Request" in exc_info.value.detail


# ---------------------------------------------------------------------------
# get_flags DI helper
# ---------------------------------------------------------------------------


async def test_get_flags_returns_disabled_everywhere_when_no_app() -> None:
    """When scope has no 'app', get_flags returns a disabled-everywhere Flags."""
    from hawkapi.requests.request import Request

    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
    }
    req = Request(scope, _dummy_receive)
    flags = await get_flags(req)
    # With empty StaticFlagProvider the default passed in is returned
    assert await flags.bool("any", True) is True


async def test_get_flags_uses_app_provider() -> None:
    """get_flags picks up app.flags from scope['app']."""
    from hawkapi import HawkAPI
    from hawkapi.requests.request import Request

    provider = StaticFlagProvider({"my-flag": True})
    hawk = HawkAPI(openapi_url=None, flags=provider)
    req = Request(_make_scope(hawk), _dummy_receive)
    flags = await get_flags(req)
    assert await flags.bool("my-flag") is True


async def test_get_flags_context_from_headers() -> None:
    """EvalContext is built from x-user-id / x-tenant-id headers."""
    from hawkapi import HawkAPI
    from hawkapi.requests.request import Request

    hawk = HawkAPI(openapi_url=None)
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(b"x-user-id", b"alice"), (b"x-tenant-id", b"acme")],
        "app": hawk,
    }
    req = Request(scope, _dummy_receive)
    flags = await get_flags(req)
    ctx = flags._context  # type: ignore[attr-defined]
    assert ctx is not None
    assert ctx.user_id == "alice"
    assert ctx.tenant_id == "acme"
