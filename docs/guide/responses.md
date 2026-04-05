# Responses

HawkAPI provides several response types for different use cases.

## JSON Response (default)

Returning a dict or `msgspec.Struct` automatically produces a JSON response:

```python
@app.get("/users")
async def list_users():
    return [{"id": 1, "name": "Alice"}]
```

## Typed Responses

```python
from hawkapi import JSONResponse, HTMLResponse, PlainTextResponse, RedirectResponse

@app.get("/html")
async def html():
    return HTMLResponse("<h1>Hello</h1>")

@app.get("/text")
async def text():
    return PlainTextResponse("plain text")

@app.get("/old")
async def redirect():
    return RedirectResponse("/new")
```

## Response Model

Filter response fields using `response_model`:

```python
import msgspec

class UserOut(msgspec.Struct):
    id: int
    name: str

@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: int):
    # Extra fields are stripped from the response
    return {"id": user_id, "name": "Alice", "password_hash": "secret"}
```

## File Response

```python
from hawkapi import FileResponse

@app.get("/download")
async def download():
    return FileResponse("report.pdf", filename="report.pdf")
```

## Streaming Response

```python
from hawkapi import StreamingResponse

async def generate():
    for i in range(100):
        yield f"chunk {i}\n"

@app.get("/stream")
async def stream():
    return StreamingResponse(generate(), content_type="text/plain")
```

## MessagePack Support

HawkAPI supports MessagePack as an alternative response format via content negotiation. When a client sends an `Accept: application/msgpack` header, the response is automatically encoded as MessagePack instead of JSON.

```python
@app.get("/data")
async def get_data():
    return {"values": [1, 2, 3]}
```

```bash
# JSON (default)
curl http://localhost:8000/data

# MessagePack
curl -H "Accept: application/msgpack" http://localhost:8000/data
```

Both `application/msgpack` and `application/x-msgpack` are accepted. The negotiation respects quality values in the `Accept` header, and falls back to JSON when no supported format is matched. MessagePack encoding uses `msgspec.msgpack` and supports the same custom types (datetime, UUID, sets, bytes) as the JSON encoder.

## Server-Sent Events

```python
from hawkapi import EventSourceResponse, ServerSentEvent

async def event_stream():
    for i in range(10):
        yield ServerSentEvent(data=f"Message {i}", event="update")

@app.get("/events")
async def events():
    return EventSourceResponse(event_stream())
```
