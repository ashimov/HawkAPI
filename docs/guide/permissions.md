# Declarative Permissions

HawkAPI provides route-level permission enforcement via `PermissionPolicy`.

## Setup

```python
from hawkapi import HawkAPI, PermissionPolicy, Request

async def get_user_permissions(request: Request) -> set[str]:
    token = request.headers.get("authorization", "")
    user = await decode_token(token)
    return user.permissions

app = HawkAPI()
app.permission_policy = PermissionPolicy(
    resolver=get_user_permissions,
    mode="all",  # require ALL listed permissions
)
```

## Protecting Routes

```python
@app.get("/admin/dashboard", permissions=["admin:read"])
async def admin_dashboard():
    return {"secret": "data"}

@app.post("/admin/users", permissions=["admin:read", "admin:write"])
async def create_admin_user(name: str):
    return {"name": name}
```

## Check Modes

- `mode="all"` (default) — user must have **all** listed permissions
- `mode="any"` — user must have **at least one** of the listed permissions

```python
app.permission_policy = PermissionPolicy(
    resolver=get_user_permissions,
    mode="any",
)
```

## WebSocket Permissions

Permissions also work on WebSocket routes. Unauthorized connections are closed with code `4003`:

```python
@app.websocket("/ws/admin", permissions=["admin:read"])
async def admin_ws(ws):
    await ws.accept()
    await ws.send_text("Welcome, admin!")
```

## OpenAPI Integration

Permissions are exposed as `x-permissions` in the OpenAPI spec:

```json
{
  "/admin/dashboard": {
    "get": {
      "x-permissions": ["admin:read"]
    }
  }
}
```
