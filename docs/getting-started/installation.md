# Installation

## Requirements

- Python 3.12+

## Basic Install

```bash
pip install hawkapi
```

## Optional Extras

| Extra | Description |
|-------|-------------|
| `pydantic` | Pydantic v2 model support |
| `granian` | Granian ASGI server |
| `uvloop` | uvloop event loop |
| `uvicorn` | Uvicorn ASGI server |
| `otel` | OpenTelemetry tracing |
| `all` | All of the above |

```bash
pip install "hawkapi[all]"
```

## Development Install

```bash
git clone https://github.com/ashimov/HawkAPI.git
cd hawkapi
pip install -e ".[dev]"
```
