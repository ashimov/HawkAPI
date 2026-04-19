# gRPC

HawkAPI ships a **thin gRPC mount** that wires a `grpc.aio` server into the
ASGI lifespan — so your gRPC service starts and stops with your HTTP server,
shares the same process, and gets built-in observability for free.

## Installation

```bash
pip install hawkapi[grpc]
# or with uv:
uv add "hawkapi[grpc]"
```

## Quickstart

### 1. Generate stubs

```bash
python -m grpc_tools.protoc \
  -I proto \
  --python_out=. \
  --grpc_python_out=. \
  proto/greeter.proto
```

This produces `greeter_pb2.py` and `greeter_pb2_grpc.py`.

### 2. Implement and mount the servicer

```python
import hawkapi
from greeter_pb2_grpc import GreeterServicer, add_GreeterServicer_to_server
from greeter_pb2 import HelloReply

app = hawkapi.HawkAPI()

class MyGreeter(GreeterServicer):
    async def SayHello(self, request, context):
        return HelloReply(message=f"Hello, {request.name}!")

app.mount_grpc(
    MyGreeter(),
    add_to_server=add_GreeterServicer_to_server,
    port=50051,
)
```

That's it. When the ASGI server starts (e.g. `uvicorn`), the gRPC server
starts on `:50051` automatically.

## ASGI lifespan integration

`mount_grpc` installs startup / shutdown hooks on the first call, so:

- **startup** — `grpc.aio.server` is created, servicers are registered, port
  is bound, and `server.start()` is awaited.
- **shutdown** — `server.stop(grace=5.0)` is awaited, draining in-flight RPCs.

Use `autostart=False` if you need manual control:

```python
mount = app.mount_grpc(
    MyGreeter(),
    add_to_server=add_GreeterServicer_to_server,
    port=50051,
    autostart=False,
)

# Later:
await mount.start()
# ...
await mount.stop(grace=10.0)
```

## Accessing the HawkAPI app from a handler

The built-in observability interceptor attaches two attributes to the
`ServicerContext` before delegating to your handler:

| Attribute | Value |
|---|---|
| `context.hawkapi_app` | The `HawkAPI` application instance |
| `context.hawkapi_request_id` | `uuid.uuid4().hex` — 32-char hex string |

```python
class MyServicer(EchoServicer):
    async def Echo(self, request, context):
        app = context.hawkapi_app          # HawkAPI instance
        rid = context.hawkapi_request_id   # e.g. "a3f2..."
        return EchoReply(message=request.message)
```

## TLS passthrough

Pass a `grpc.ServerCredentials` object — HawkAPI calls
`server.add_secure_port()` for you:

```python
import grpc

credentials = grpc.ssl_server_credentials(
    [(open("server.key", "rb").read(), open("server.crt", "rb").read())]
)

app.mount_grpc(
    MyGreeter(),
    add_to_server=add_GreeterServicer_to_server,
    port=50051,
    ssl_credentials=credentials,
)
```

## Reflection

Enable [gRPC server reflection](https://github.com/grpc/grpc/blob/master/doc/server-reflection.md)
so tools like `grpcurl` can discover your services at runtime.

Requires `pip install hawkapi[grpc]` (includes `grpcio-reflection`).

```python
from grpc_reflection.v1alpha import reflection

app.mount_grpc(
    MyGreeter(),
    add_to_server=add_GreeterServicer_to_server,
    port=50051,
    reflection=True,
    reflection_service_names=[
        "greeter.Greeter",          # your service name
        reflection.SERVICE_NAME,    # the reflection service itself
    ],
)
```

!!! note
    `reflection_service_names` is **required** when `reflection=True`.
    A `ConfigurationError` is raised with a clear message if it is omitted.

## Observability

### Structured logs

The built-in interceptor emits two `INFO` log records per RPC to
`logging.getLogger("hawkapi.grpc")`:

```json
{"event": "grpc.request",  "method": "/greeter.Greeter/SayHello", "peer": "ipv6:[::1]:54321", "request_id": "a3f2..."}
{"event": "grpc.response", "method": "/greeter.Greeter/SayHello", "code": "OK", "duration_ms": 1.234}
```

### Prometheus metrics

When `prometheus_client` is installed, two metrics are registered globally:

| Metric | Type | Labels |
|---|---|---|
| `hawkapi_grpc_requests_total` | Counter | `method`, `code` |
| `hawkapi_grpc_request_duration_seconds` | Histogram | `method` |

Metrics are created once (idempotent) — safe to import in tests multiple times.

### Disabling observability

```python
app.mount_grpc(
    MyGreeter(),
    add_to_server=add_GreeterServicer_to_server,
    observability=False,   # skip the built-in interceptor entirely
)
```

## Multiple services on one port

Call `mount_grpc` twice with the **same port** — servicers are merged onto one
`grpc.aio.Server`:

```python
mount_a = app.mount_grpc(GreeterServicer(), add_to_server=add_GreeterServicer_to_server, port=50051)
mount_b = app.mount_grpc(EchoServicer(),    add_to_server=add_EchoServicer_to_server,    port=50051)
assert mount_a is mount_b   # same server
```

## Custom interceptors

Pass additional `grpc.aio.ServerInterceptor` instances via `interceptors=`.
The built-in observability interceptor always runs **first**:

```python
from my_auth import AuthInterceptor

app.mount_grpc(
    MyGreeter(),
    add_to_server=add_GreeterServicer_to_server,
    interceptors=[AuthInterceptor()],
)
```

## Full signature reference

```python
app.mount_grpc(
    servicer,                         # your servicer object
    add_to_server=add_Foo_to_server,  # generated registration function
    port=50051,                       # TCP port (default 50051)
    host="[::]",                      # bind address (default all interfaces)
    interceptors=(),                  # extra ServerInterceptor instances
    observability=True,               # built-in interceptor (default on)
    reflection=False,                 # gRPC server reflection
    reflection_service_names=None,    # required when reflection=True
    ssl_credentials=None,             # grpc.ServerCredentials for TLS
    autostart=True,                   # start on ASGI lifespan (default on)
    max_workers=None,                 # reserved, currently unused
    options=(),                       # grpc channel options
)
```

Returns a `GrpcMount` with:

- `.server` — the underlying `grpc.aio.Server` (available after start)
- `.port` — bound port
- `.start()` — async, idempotent
- `.stop(grace=5.0)` — async, safe no-op if not started

## Roadmap

- Bi-directional streaming support (infrastructure is in place; tests cover unary + server-streaming)
- Per-mount Prometheus registry (currently uses the default global registry)
- Health checking protocol (`grpc.health.v1`)
