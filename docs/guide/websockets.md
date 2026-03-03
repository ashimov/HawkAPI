# WebSockets

HawkAPI provides first-class WebSocket support.

## Basic Usage

```python
from hawkapi import HawkAPI, WebSocket

app = HawkAPI()

@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    while True:
        text = await ws.receive_text()
        await ws.send_text(f"Echo: {text}")
```

## Sending and Receiving

```python
@app.websocket("/ws")
async def handler(ws: WebSocket):
    await ws.accept()

    # Text
    text = await ws.receive_text()
    await ws.send_text("hello")

    # Binary
    data = await ws.receive_bytes()
    await ws.send_bytes(b"\x00\x01")

    # JSON
    obj = await ws.receive_json()
    await ws.send_json({"status": "ok"})

    await ws.close()
```

## Iterating Messages

```python
@app.websocket("/ws")
async def handler(ws: WebSocket):
    await ws.accept()
    async for message in ws:
        await ws.send_text(f"Got: {message}")
```

## Handling Disconnects

```python
from hawkapi import WebSocketDisconnect

@app.websocket("/ws")
async def handler(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_text()
            await ws.send_text(data)
    except WebSocketDisconnect:
        print("Client disconnected")
```

## Protected WebSockets

WebSocket routes support permission checks (see [Permissions](permissions.md)):

```python
@app.websocket("/ws/admin", permissions=["admin:read"])
async def admin_ws(ws: WebSocket):
    await ws.accept()
    await ws.send_text("Welcome")
```

Unauthorized connections are closed with code `4003`.
