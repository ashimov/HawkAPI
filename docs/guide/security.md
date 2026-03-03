# Security

HawkAPI provides authentication schemes that integrate with OpenAPI.

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
