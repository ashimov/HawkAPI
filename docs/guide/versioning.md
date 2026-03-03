# API Versioning

HawkAPI supports URL-based API versioning with `VersionRouter`.

## VersionRouter

```python
from hawkapi import HawkAPI, VersionRouter

app = HawkAPI()

v1 = VersionRouter("v1")
v2 = VersionRouter("v2")

@v1.get("/users")
async def list_users_v1():
    return [{"id": 1, "name": "Alice"}]

@v2.get("/users")
async def list_users_v2():
    return [{"id": 1, "name": "Alice", "email": "alice@example.com"}]

app.include_router(v1)
app.include_router(v2)
# GET /v1/users -> list_users_v1
# GET /v2/users -> list_users_v2
```

## Per-Route Version

```python
@app.get("/users", version="v1")
async def list_users():
    return []
```

## Per-Version OpenAPI

Generate OpenAPI specs filtered by version:

```python
spec_v1 = app.openapi(api_version="v1")
spec_v2 = app.openapi(api_version="v2")
```

## Breaking Changes Detection

Compare two OpenAPI specs to detect breaking changes:

```python
from hawkapi import detect_breaking_changes

old_spec = app_v1.openapi()
new_spec = app_v2.openapi()

changes = detect_breaking_changes(old_spec, new_spec)
for change in changes:
    print(f"[{change.severity.value}] {change.description}")
```

Detected changes include: paths removed, methods removed, required parameters added, parameter types changed, response fields removed, and status codes changed.
