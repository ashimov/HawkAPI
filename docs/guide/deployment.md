# Deployment Guide

This guide covers deploying HawkAPI applications to production using Docker.

## Quick Start

Copy the template files into your project:

```bash
cp templates/Dockerfile .
cp templates/docker-compose.yml .
```

Build and run:

```bash
docker compose up --build
```

Your app is now available at `http://localhost:8000`.

## Dockerfile Walkthrough

The template uses a **multi-stage build** for minimal image size:

1. **Builder stage** — installs `uv`, resolves dependencies, copies source.
2. **Runtime stage** — copies only the virtualenv and source. No build tools in the final image.

Key features:

- **Non-root user** (`app`) — prevents privilege escalation.
- **Layer caching** — `pyproject.toml` is copied before source, so dependency install is cached unless deps change.
- **Health check** — uses HawkAPI's built-in `/healthz` endpoint.

## Choosing a Server

### Uvicorn (default)

```dockerfile
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

Install: `pip install hawkapi[uvicorn]`

### Granian (Rust-based, faster)

```dockerfile
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "src.app:app"]
```

Install: `pip install hawkapi[granian]`

## Worker Count

Rule of thumb: **2 × CPU cores + 1**.

| CPU Cores | Workers |
|-----------|---------|
| 1         | 3       |
| 2         | 5       |
| 4         | 9       |
| 8         | 17      |

For I/O-bound apps (database queries, external APIs), you can increase this. For CPU-bound apps, stay closer to core count.

## Environment Variables

Use `hawkapi.config.Settings` to manage environment variables:

```python
from hawkapi import Settings, env_field

class AppSettings(Settings):
    database_url: str = env_field("DATABASE_URL")
    redis_url: str = env_field("REDIS_URL", default="redis://localhost:6379/0")
    debug: bool = env_field("DEBUG", default=False)
```

Pass variables via `docker-compose.yml` or `-e` flags.

## Health Checks

HawkAPI auto-registers a `/healthz` endpoint (configurable via `health_url`):

```python
app = HawkAPI(health_url="/healthz")  # default
app = HawkAPI(health_url=None)        # disable
```

The Dockerfile HEALTHCHECK uses this endpoint. Docker and orchestrators (Kubernetes, ECS) use health checks for restart decisions.

## Graceful Shutdown

HawkAPI supports lifespan hooks for graceful startup and shutdown:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    # Startup: open connections
    db = await create_db_pool()
    yield
    # Shutdown: close connections
    await db.close()

app = HawkAPI(lifespan=lifespan)
```

Docker sends `SIGTERM` on stop. Uvicorn/Granian handle this and trigger the shutdown hook.

## Production Tips

1. **Read-only filesystem** — mount source as read-only where possible.
2. **Resource limits** — set memory and CPU limits in docker-compose or your orchestrator.
3. **Logging** — use `StructuredLoggingMiddleware` for JSON logs compatible with log aggregators.
4. **Metrics** — use `PrometheusMiddleware` for monitoring with Grafana/Prometheus.
5. **TLS** — terminate TLS at a reverse proxy (nginx, Caddy, cloud load balancer), not in the app.
6. **uvloop** — install `hawkapi[uvloop]` for faster event loop (Linux only).

```yaml
# docker-compose.yml production overrides
services:
  app:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "2.0"
    read_only: true
    tmpfs:
      - /tmp
```
