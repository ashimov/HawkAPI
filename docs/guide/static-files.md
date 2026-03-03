# Static Files

Serve static files from a directory with automatic caching headers.

## Basic Usage

```python
from hawkapi import HawkAPI, StaticFiles

app = HawkAPI()
app.mount("/static", StaticFiles(directory="static"))
```

## Caching

StaticFiles automatically sets caching headers:

- **ETag** — weak ETag based on file modification time and size
- **Last-Modified** — file modification timestamp
- **Cache-Control** — configurable max-age (default: 3600 seconds)
- **304 Not Modified** — conditional responses for `If-None-Match` and `If-Modified-Since`

```python
# Custom max-age (24 hours)
app.mount("/static", StaticFiles(directory="static", max_age=86400))
```

## HTML Mode

Serve `index.html` automatically for directory requests:

```python
app.mount("/", StaticFiles(directory="public", html=True))
```

## Security

StaticFiles includes built-in path traversal protection using `Path.is_relative_to()`, so directory escape attempts like `../../etc/passwd` are blocked with a 404 response.
