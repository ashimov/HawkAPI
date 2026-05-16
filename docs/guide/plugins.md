# Official plugins

HawkAPI ships a small, focused core. Everything else — auth, mail, cache, file storage, an admin UI — lives in optional packages under the `hawkapi-*` namespace. Install only what you need; every plugin follows the same `init_xxx(app, ...)` + `Depends(get_xxx)` pattern.

## Observability

| Package | Install | Purpose |
| --- | --- | --- |
| [`hawkapi-sentry`](https://pypi.org/project/hawkapi-sentry/) | `pip install hawkapi-sentry` | Sentry SDK integration — exceptions, traces, request context |
| [`hawkapi-otel`](https://pypi.org/project/hawkapi-otel/) | `pip install hawkapi-otel` | OpenTelemetry — auto-instrumentation, traces, metrics, logs |

## Auth & security

| Package | Install | Purpose |
| --- | --- | --- |
| [`hawkapi-auth`](https://pypi.org/project/hawkapi-auth/) | `pip install hawkapi-auth` | JWT (access + refresh), argon2id passwords, DI guards, scopes |

## Data layer

| Package | Install | Purpose |
| --- | --- | --- |
| [`hawkapi-sqlalchemy`](https://pypi.org/project/hawkapi-sqlalchemy/) | `pip install hawkapi-sqlalchemy` | Async SQLAlchemy 2.0 — sessions in DI, multi-DB routing (primary/replica/shards), `Base`/`TimestampMixin`/`UUIDMixin`, Alembic helper, pytest fixtures |
| [`hawkapi-cache`](https://pypi.org/project/hawkapi-cache/) | `pip install hawkapi-cache` | Response caching with TTL + tag-based invalidation; in-memory and Redis backends |
| [`hawkapi-storage`](https://pypi.org/project/hawkapi-storage/) | `pip install hawkapi-storage` | Pluggable file storage — local, S3 (incl. MinIO/R2/Wasabi), GCS, Azure; streaming + pre-signed URLs |

## Messaging & integration

| Package | Install | Purpose |
| --- | --- | --- |
| [`hawkapi-mail`](https://pypi.org/project/hawkapi-mail/) | `pip install hawkapi-mail` | Email backends (SMTP, SES, SendGrid, Mailgun, Resend), Jinja2 templates, persistent outbox + retry, webhook handlers for bounce/complaint events |
| [`hawkapi-celery`](https://pypi.org/project/hawkapi-celery/) | `pip install hawkapi-celery` | Celery integration — `@task` decorator (async-aware), beat schedule helpers, broker/worker healthchecks, request-context propagation, eager-mode fixtures |
| [`hawkapi-websockets`](https://pypi.org/project/hawkapi-websockets/) | `pip install hawkapi-websockets` | Connection manager with rooms + broadcasting; optional Redis pub/sub backplane for multi-process fan-out; heartbeat monitor |
| [`hawkapi-mcp`](https://pypi.org/project/hawkapi-mcp/) | `pip install hawkapi-mcp` | Model Context Protocol server — expose your routes as MCP tools to LLM agents |

## Admin

| Package | Install | Purpose |
| --- | --- | --- |
| [`hawkapi-admin`](https://pypi.org/project/hawkapi-admin/) | `pip install hawkapi-admin` | Auto-generated CRUD admin UI for hawkapi-sqlalchemy models — list, detail, create, edit, delete; type-driven widgets; search; pagination; light/dark CSS |

## A taste of the patterns

Every plugin follows the same shape — register at app startup, inject in handlers:

```python
from hawkapi import Depends, HawkAPI
from hawkapi_auth import init_auth, JWTConfig, random_secret, requires_user
from hawkapi_sqlalchemy import init_database, get_session
from hawkapi_cache import init_cache, cached
from hawkapi_storage import LocalConfig, LocalStorage, init_storage, get_storage

app = HawkAPI()
init_auth(app, config=JWTConfig(secret=random_secret()))
init_database(app, url="postgresql+asyncpg://...")
init_cache(app)
init_storage(app, storage=LocalStorage(LocalConfig(root="/var/data")))


@app.get("/me")
@cached(ttl=60)
async def me(user_id: str = Depends(requires_user)):
    ...
```

## Roadmap (not yet shipped)

Candidate plugins that fit the same pattern but haven't been built yet. Open an issue if one would unblock you:

- **hawkapi-ratelimit** — token bucket + sliding window with Redis
- **hawkapi-cron** — in-process scheduler without a Celery dependency
- **hawkapi-pagination** — cursor + offset helpers, `Page[T]` response model
- **hawkapi-csrf** — CSRF for form-based flows (pairs with `hawkapi-admin`)
- **hawkapi-i18n** — gettext + `Accept-Language` + lazy strings
- **hawkapi-sse** — Server-Sent Events
- **hawkapi-redis** / **hawkapi-mongo** / **hawkapi-clickhouse** / **hawkapi-kafka** / **hawkapi-search** — generic clients with DI + healthchecks
- **hawkapi-webhook** — outbound webhooks with retry + HMAC signing
- **hawkapi-events** — outbox pattern + domain event bus
- **hawkapi-cli** — manage.py-style CLI (migrate, shell, run-jobs)
- **hawkapi-payments** — Stripe + PayPal wrappers
