# Python SDK Generation

This guide covers generating type-safe Python clients from HawkAPI's OpenAPI specification.

## Prerequisites

- Python 3.8+
- HawkAPI instance with OpenAPI schema exposed at `/openapi.json`

## Method 1: openapi-generator-cli with python Generator

The standard approach using the OpenAPI Generator framework.

### Installation

```bash
# Via Homebrew (macOS)
brew install openapi-generator

# Via npm
npm install @openapitools/openapi-generator-cli -g

# Via Docker
docker run --rm -v /local/path:/local/path openapitools/openapi-generator-cli generate \
  -i /local/path/openapi.json \
  -g python \
  -o /local/path/sdk
```

### Configuration

Create `openapitools.json`:

```json
{
  "packageName": "hawkapi_client",
  "packageVersion": "1.0.0",
  "projectName": "hawkapi-client",
  "gitUserId": "your-org",
  "gitRepoId": "hawkapi-client-python"
}
```

### Generate SDK

```bash
# From running HawkAPI instance
openapi-generator-cli generate \
  -i http://localhost:8000/openapi.json \
  -g python \
  -o ./sdk \
  -c openapitools.json

# From saved schema file
openapi-generator-cli generate \
  -i ./openapi.json \
  -g python \
  -o ./sdk \
  -c openapitools.json
```

### Output Structure

```
sdk/
├── hawkapi_client/
│   ├── models/           # Generated model classes
│   ├── api/              # Generated API client classes
│   ├── configuration.py  # Client configuration
│   └── __init__.py
├── setup.py
└── requirements.txt
```

### Install Generated SDK

```bash
cd sdk
pip install -e .
```

### Usage

```python
from hawkapi_client import ApiClient, Configuration
from hawkapi_client.api.default_api import DefaultApi
from hawkapi_client.models import User, CreateUserRequest

# Configure client
config = Configuration(host="http://localhost:8000")
client = ApiClient(config)
api = DefaultApi(client)

# Call generated methods with full type safety
users = api.list_users()
new_user = api.create_user(CreateUserRequest(name="Alice"))

print(new_user.id)
```

### Advanced Configuration

Add to `openapitools.json` for customization:

```json
{
  "packageName": "hawkapi_client",
  "packageVersion": "1.0.0",
  "packageUrl": "https://github.com/your-org/hawkapi-client-python",
  "projectName": "hawkapi-client",
  "useOneOfDiscriminatorLookup": true,
  "supportPython3": true,
  "modelPropertyNaming": "snake_case",
  "generateSourceCodeOnly": true,
  "hideGenerationTimestamp": true
}
```

## Method 2: httpx + msgspec Custom Client

Lightweight approach using HawkAPI's preferred stack for maximum performance.

### Installation

```bash
pip install httpx msgspec pydantic
```

### Schema Generation with dataclasses-json

First, generate models from OpenAPI:

```bash
# Install datamodel-code-generator
pip install datamodel-code-generator

# Generate Python models
datamodel-code-generator \
  --input openapi.json \
  --input-file-type openapi \
  --output models.py
```

Or manually define models:

```python
# hawkapi_client/models.py
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class User:
    id: int
    name: str
    email: str

@dataclass
class CreateUserRequest:
    name: str
    email: str

@dataclass
class UpdateUserRequest:
    name: Optional[str] = None
    email: Optional[str] = None
```

### Custom Client Implementation

```python
# hawkapi_client/client.py
import httpx
import msgspec
from typing import TypeVar, Generic, Type, Optional, Dict, Any
from dataclasses import asdict
from urllib.parse import urlencode

from .models import User, CreateUserRequest, UpdateUserRequest

T = TypeVar('T')

class APIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")

class HawkAPIClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers=headers or {},
        )
        self.encoder = msgspec.json.Encoder()
        self.decoder = msgspec.json.Decoder()

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Any] = None,
        query: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Make HTTP request with proper error handling."""
        url = f"{self.base_url}{path}"

        if query:
            query_str = urlencode({k: str(v) for k, v in query.items()})
            url = f"{url}?{query_str}"

        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)

        body = None
        if json is not None:
            body = self.encoder.encode(json).decode('utf-8')

        response = await self.client.request(
            method,
            url,
            content=body,
            headers=req_headers,
        )

        if not response.is_success:
            text = response.text
            raise APIError(response.status_code, text)

        return response

    async def _parse_response(self, response: httpx.Response, model: Type[T]) -> T:
        """Parse response body into model."""
        data = response.json()
        # For dataclasses, use msgspec or pydantic
        return msgspec.json.decode(msgspec.json.encode(data), type=model)

    # User API Methods
    async def list_users(self) -> list[User]:
        """List all users."""
        response = await self.request("GET", "/users")
        return response.json()

    async def get_user(self, user_id: int) -> User:
        """Get user by ID."""
        response = await self.request("GET", f"/users/{user_id}")
        return response.json()

    async def create_user(self, request: CreateUserRequest) -> User:
        """Create a new user."""
        response = await self.request(
            "POST",
            "/users",
            json=asdict(request),
        )
        return response.json()

    async def update_user(
        self,
        user_id: int,
        request: UpdateUserRequest,
    ) -> User:
        """Update user by ID."""
        data = {k: v for k, v in asdict(request).items() if v is not None}
        response = await self.request(
            "PUT",
            f"/users/{user_id}",
            json=data,
        )
        return response.json()

    async def delete_user(self, user_id: int) -> None:
        """Delete user by ID."""
        await self.request("DELETE", f"/users/{user_id}")

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
```

### Usage

```python
import asyncio
from hawkapi_client import HawkAPIClient, CreateUserRequest

async def main():
    async with HawkAPIClient("http://localhost:8000") as client:
        # List users
        users = await client.list_users()
        print(f"Found {len(users)} users")

        # Create user
        new_user = await client.create_user(
            CreateUserRequest(name="Alice", email="alice@example.com")
        )
        print(f"Created user: {new_user.id}")

        # Get specific user
        user = await client.get_user(new_user.id)
        print(f"User: {user.name}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Method 3: Synchronous httpx Client

For synchronous code:

```python
# hawkapi_client/sync_client.py
import httpx
from typing import Optional, Dict, Any

class HawkAPIClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip('/')
        self.client = httpx.Client(timeout=timeout)

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Any] = None,
        query: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """Make HTTP request."""
        url = f"{self.base_url}{path}"

        if query:
            response = self.client.request(
                method,
                url,
                params=query,
                json=json,
            )
        else:
            response = self.client.request(method, url, json=json)

        if not response.is_success:
            raise APIError(response.status_code, response.text)

        return response

    def list_users(self):
        return self.request("GET", "/users").json()

    def get_user(self, user_id: int):
        return self.request("GET", f"/users/{user_id}").json()

    def create_user(self, data: dict):
        return self.request("POST", "/users", json=data).json()

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
```

### Usage

```python
from hawkapi_client import HawkAPIClient

with HawkAPIClient("http://localhost:8000") as client:
    users = client.list_users()
    print(users)

    new_user = client.create_user({
        "name": "Alice",
        "email": "alice@example.com"
    })
    print(new_user)
```

## Publishing to PyPI

Once developed and tested:

```bash
# Setup
pip install build twine

# Build distribution
python -m build

# Test locally
pip install dist/hawkapi_client-1.0.0-py3-none-any.whl

# Upload to PyPI
python -m twine upload dist/*
```

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "hawkapi-client"
version = "1.0.0"
description = "Type-safe Python client for HawkAPI"
requires-python = ">=3.8"
dependencies = [
    "httpx>=0.24.0",
    "msgspec>=0.18.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21.0",
    "ruff>=0.1.0",
]
```

## Recommendations

- **Full SDK**: Use `openapi-generator-cli` for enterprise applications with extensive API coverage
- **Custom httpx**: Use the httpx + msgspec approach for performance-critical applications
- **Type Safety**: Use either `msgspec`, `pydantic`, or `dataclasses` for model validation
- **Async Support**: Prefer async clients (`httpx.AsyncClient`) for modern Python applications
- **Schema Updates**: Regenerate or update models whenever HawkAPI schema changes

## Troubleshooting

### Generator installation issues
```bash
# Ensure Java is installed (required for openapi-generator-cli)
java -version

# Install via HomeBrew
brew install openapi-generator
```

### Import errors after generation
- Ensure the generated package is in your Python path
- Install with `pip install -e .` for development
- Check `__init__.py` files are present in all packages

### Type checking errors
- Use `pyright` or `mypy` for type validation
- Ensure generated models have proper type hints
- Consider using `pydantic` for runtime validation

### httpx/msgspec compatibility
- Ensure msgspec >= 0.18 for best performance
- Use `httpx >= 0.24.0` for latest features
- Python 3.8+ required for all modern features
