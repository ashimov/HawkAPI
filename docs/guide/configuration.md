# Configuration

## Application Settings

Configure the application in the constructor:

```python
from hawkapi import HawkAPI

app = HawkAPI(
    title="My API",
    version="1.0.0",
    description="My awesome API",
    health_url="/healthz",           # Health check endpoint (None to disable)
    request_timeout=30.0,            # Request timeout in seconds (504 on timeout)
    max_body_size=10 * 1024 * 1024,  # 10 MB request body limit
    serverless=True,                 # Skip docs routes for faster cold start
)
```

## Health Check

A built-in health check endpoint is enabled by default at `/healthz`:

```python
# Default: GET /healthz returns {"status": "ok"}
app = HawkAPI(health_url="/healthz")

# Custom path
app = HawkAPI(health_url="/health")

# Disable health check
app = HawkAPI(health_url=None)
```

## Request Timeout

Automatically return 504 Gateway Timeout for slow handlers:

```python
app = HawkAPI(request_timeout=10.0)  # 10 second timeout
```

## Graceful Shutdown

HawkAPI tracks in-flight requests and waits for them to complete during shutdown:

```python
app = HawkAPI(shutdown_drain_timeout=30.0)  # Wait up to 30s for in-flight requests
```

## Settings Class

For environment-based configuration, use the `Settings` base class:

```python
from hawkapi import Settings, env_field

class AppSettings(Settings):
    debug: bool = False
    database_url: str = env_field("DATABASE_URL")
    redis_url: str = env_field("REDIS_URL", default="redis://localhost")
    workers: int = env_field("WORKERS", default=4)

    class Config:
        env_prefix = "APP_"
        env_file = ".env"

settings = AppSettings.load()
```

### Profile Support

Load settings per environment:

```python
# Loads from .env.production
settings = AppSettings.load(profile="production")
```
