# HTTP/2 and HTTPS

HawkAPI is an ASGI application — HTTP protocol negotiation is handled by the
ASGI server. Granian supports HTTP/1.1, HTTP/2 (with TLS), and (experimental)
HTTP/3. Uvicorn supports HTTP/1.1 and HTTP/2 via `httptools`.

## Why HTTP/2

- **Multiplexing**: many requests on one TCP connection — eliminates head-of-line
  blocking and connection setup latency.
- **Header compression** (HPACK): redundant headers (e.g., cookies) sent once.
- **Server push** (deprecated in browsers but useful for gRPC and internal calls).
- **Smaller per-request overhead** at scale.

For typical REST APIs the throughput improvement is modest, but **p99 latency
under high concurrency** drops noticeably.

## Run with Granian (HTTP/2 + TLS)

```bash
uv pip install hawkapi[granian]

granian \
  --interface asgi \
  --http 2 \
  --ssl-keyfile path/to/key.pem \
  --ssl-certfile path/to/cert.pem \
  myapp:app
```

HTTP/2 over TLS is the only browser-supported variant. For internal traffic
between services you may use h2c (HTTP/2 cleartext):

```bash
granian --interface asgi --http 2 --no-tls myapp:app
```

## Run with Uvicorn

```bash
uv pip install hawkapi[uvicorn]

uvicorn myapp:app --http httptools --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Uvicorn negotiates HTTP/2 automatically when TLS ALPN advertises `h2`.

## Self-signed certs for local dev

```bash
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 365 \
  -subj '/CN=localhost'
```

Then visit `https://localhost:8000` and accept the warning.

## Verify HTTP/2 is active

```bash
curl --http2 -I https://localhost:8000/json -k
# Look for: HTTP/2 200
```

Or in browser dev tools, the **Protocol** column should show `h2`.

## HawkAPI behavior under HTTP/2

- All endpoints work transparently — no code changes needed.
- WebSockets continue to use HTTP/1.1 upgrade (HTTP/2 WebSocket is a separate
  RFC and not yet broadly supported).
- Server-Sent Events work over both HTTP/1.1 and HTTP/2; HTTP/2 multiplexing
  removes the 6-connection-per-domain browser limit.
- `Request.scope["http_version"]` reports `"2"` under HTTP/2.

## HTTP/3 (experimental)

Granian ships an experimental HTTP/3 backend via `aioquic`:

```bash
granian --interface asgi --http 3 \
  --ssl-keyfile key.pem --ssl-certfile cert.pem \
  myapp:app
```

HTTP/3 requires UDP port 443 (or another high port) accessible — ensure your
firewall allows it. Browsers fall back to HTTP/2 if HTTP/3 negotiation fails.
