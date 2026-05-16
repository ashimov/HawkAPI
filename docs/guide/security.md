# Security

HawkAPI provides authentication schemes that integrate with OpenAPI.

!!! warning "Comparing credentials safely"
    All built-in schemes (`HTTPBasic`, `HTTPBearer`, `APIKey*`,
    `OAuth2PasswordBearer`) only *extract* credentials from the request.
    Comparing the extracted value against your stored secret is **your**
    responsibility. Always use a constant-time helper:

    ```python
    import secrets

    if not secrets.compare_digest(creds.password, stored_hash):
        raise HTTPException(401, detail="Invalid credentials")
    ```

    A plain `==` comparison leaks timing information and lets an attacker
    discover the secret one byte at a time.

For threat-model, OWASP API Top 10 compliance map, and responsible-disclosure
policy see:

- [`SECURITY.md`](https://github.com/ashimov/HawkAPI/blob/main/SECURITY.md) — disclosure policy
- [`docs/security/threat-model.md`](../security/threat-model.md) — STRIDE per subsystem
- [`docs/security/owasp-api-top10-2023.md`](../security/owasp-api-top10-2023.md) — compliance map
- `hawkapi doctor app:app` — lint 18 production-readiness rules

## HTTP Bearer

```python
from hawkapi import Depends, HawkAPI, HTTPBearer, HTTPBearerCredentials

app = HawkAPI()
bearer = HTTPBearer()

@app.get("/secure")
async def secure(token: HTTPBearerCredentials = Depends(bearer)):
    return {"token": token.credentials}
```

## HTTP Basic

```python
from hawkapi import HTTPBasic, HTTPBasicCredentials, Depends

basic = HTTPBasic()

@app.get("/login")
async def login(creds: HTTPBasicCredentials = Depends(basic)):
    return {"user": creds.username}
```

## OAuth2 Password Bearer

```python
from hawkapi import OAuth2PasswordBearer, Depends

oauth2 = OAuth2PasswordBearer(token_url="/auth/token")

@app.get("/users/me")
async def me(token: str = Depends(oauth2)):
    user = await verify_token(token)
    return user
```

## API Key

```python
from hawkapi import APIKeyHeader, Depends

api_key = APIKeyHeader(name="X-API-Key")

@app.get("/data")
async def get_data(key: str = Depends(api_key)):
    return {"key_prefix": key[:4]}
```

API keys can also be read from query parameters (`APIKeyQuery`) or cookies (`APIKeyCookie`).

## CSRF Protection

HawkAPI includes built-in CSRF protection via `CSRFMiddleware`, which implements the double-submit cookie pattern. See the [Middleware guide](middleware.md#csrf-middleware) for configuration options and usage examples.
