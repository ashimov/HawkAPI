# Feature Flags

HawkAPI ships a first-class feature-flag subsystem with zero mandatory external dependencies. You get three built-in providers, a request-scoped `Flags` facade, a `Depends(get_flags)` DI helper, and a `@requires_flag` handler decorator.

---

## Quick start

```python
from hawkapi import HawkAPI, Depends
from hawkapi.flags import Flags, StaticFlagProvider, get_flags

provider = StaticFlagProvider({"new-checkout": True, "dark-mode": False})
app = HawkAPI(flags=provider)

@app.get("/checkout")
async def checkout(flags: Flags = Depends(get_flags)):
    if await flags.bool("new-checkout"):
        return {"flow": "v2"}
    return {"flow": "v1"}
```

`get_flags` automatically builds an `EvalContext` from the incoming request headers (`x-user-id`, `x-tenant-id`) and returns a `Flags` instance backed by `app.flags`.

---

## Built-in providers

### StaticFlagProvider

Dict-backed, read-only after construction. Ideal for tests and simple deployments.

```python
from hawkapi.flags import StaticFlagProvider

provider = StaticFlagProvider({
    "new-ui": True,
    "rate-limit": 100,
    "theme": "dark",
})
```

Type coercion rules:

| Stored type   | `get_bool` | `get_string` | `get_number` |
|---------------|-----------|-------------|-------------|
| `bool`        | as-is     | default     | default     |
| `int`/`float` | `bool(v)` | default     | `float(v)`  |
| `str`         | default   | as-is       | default     |

### EnvFlagProvider

Reads flags from environment variables. The env-var name is built as:

```
prefix + key.upper().replace(".", "_").replace("-", "_")
```

Default prefix: `HAWKAPI_FLAG_`.

```python
from hawkapi.flags import EnvFlagProvider

# HAWKAPI_FLAG_NEW_CHECKOUT=true  ->  await flags.bool("new-checkout") == True
app = HawkAPI(flags=EnvFlagProvider())
```

Bool parsing: `1/true/yes/on` -> `True`; `0/false/no/off` -> `False`; anything else -> `default`.

Custom prefix:

```python
EnvFlagProvider(prefix="MY_APP_FLAG_")
```

### FileFlagProvider

Loads flags from a `.json`, `.toml`, `.yaml`, or `.yml` file with **mtime-based hot-reload** — no background thread required. The file is re-read only when its modification time changes.

```python
from hawkapi.flags import FileFlagProvider

app = HawkAPI(flags=FileFlagProvider("config/flags.json"))
```

**JSON** (`flags.json`):
```json
{
  "new-checkout": true,
  "rate-limit": 100,
  "theme": "dark"
}
```

**TOML** (`flags.toml`, Python 3.11+ stdlib `tomllib`):
```toml
new-checkout = true
rate-limit = 100
theme = "dark"
```

**YAML** (`flags.yaml`, requires `pip install pyyaml`):
```yaml
new-checkout: true
rate-limit: 100
theme: dark
```

!!! note
    YAML support requires `pyyaml`. If you call `get_bool/string/number` on a `.yaml`/`.yml`
    file without it installed, a clear `ImportError` is raised with install instructions.

---

## EvalContext

Every evaluation optionally carries an `EvalContext` — a frozen dataclass with per-request targeting data.

```python
from hawkapi.flags import EvalContext

ctx = EvalContext(
    user_id="alice",
    tenant_id="acme",
    attrs={"plan": "enterprise"},
)
```

`get_flags` auto-populates `user_id` and `tenant_id` from `x-user-id` / `x-tenant-id` request headers. Custom providers can use these fields to implement percentage rollouts, user allowlists, and tenant overrides.

---

## The Flags facade

`Flags` wraps any `FlagProvider` and adds:

- `.bool(key, default=False)` — evaluate a boolean flag
- `.string(key, default="")` — evaluate a string flag
- `.number(key, default=0.0)` — evaluate a numeric flag
- `.require(key)` — raises `FlagDisabled` if the flag is falsy

```python
from hawkapi.flags import FlagDisabled
from hawkapi.exceptions import HTTPException

@app.get("/beta")
async def beta_endpoint(flags: Flags = Depends(get_flags)):
    try:
        await flags.require("beta-access")
    except FlagDisabled:
        raise HTTPException(403, "Beta access not enabled")
    return {"beta": True}
```

---

## @requires_flag decorator

Gate an entire handler behind a flag — 404 (configurable) when it is off:

```python
from hawkapi.flags import requires_flag
from hawkapi.requests import Request

@app.get("/new-feature")
@requires_flag("new-feature")
async def new_feature(request: Request):
    return {"enabled": True}
```

Custom status code:

```python
@requires_flag("beta", status_code=403)
async def beta_handler(request: Request): ...
```

!!! warning
    The handler **must** accept a `request: Request` parameter (positional or keyword).
    If no `Request` is found at call time, an HTTP 500 is raised immediately (fail-closed).

---

## Plugin hook: on_flag_evaluated

Any plugin registered with `app.add_plugin(...)` can implement `on_flag_evaluated` to observe every flag evaluation — useful for telemetry:

```python
class FlagAuditPlugin:
    def on_flag_evaluated(self, key: str, value, context) -> None:
        metrics.increment("flag.evaluated", tags={"key": key})
```

Async hooks are fire-and-forget via `asyncio.create_task`. Exceptions in hooks are silently swallowed — hooks can never break flag evaluation.

---

## Writing a custom provider

Implement the `FlagProvider` protocol:

```python
from hawkapi.flags import FlagProvider, EvalContext

class MyProvider:
    async def get_bool(self, key: str, default: bool, *, context: EvalContext | None = None) -> bool:
        ...

    async def get_string(self, key: str, default: str, *, context: EvalContext | None = None) -> str:
        ...

    async def get_number(self, key: str, default: float, *, context: EvalContext | None = None) -> float:
        ...

app = HawkAPI(flags=MyProvider())
```

---

## Testing with flags

Use `StaticFlagProvider` to control flags deterministically in tests:

```python
from hawkapi.flags import StaticFlagProvider
from hawkapi.testing import TestClient

def test_new_checkout_enabled():
    provider = StaticFlagProvider({"new-checkout": True})
    app = HawkAPI(flags=provider)

    @app.get("/checkout")
    async def checkout(flags: Flags = Depends(get_flags)):
        return {"flow": "v2" if await flags.bool("new-checkout") else "v1"}

    client = TestClient(app)
    resp = client.get("/checkout")
    assert resp.json()["flow"] == "v2"
```

---

## Roadmap

- Remote provider (HTTP polling with TTL cache)
- OpenFeature SDK adapter
- Percentage-rollout rule engine built into `EvalContext`
- Streaming flag updates via SSE/WebSocket
