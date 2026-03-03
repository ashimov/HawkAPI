"""Tests for OpenAPI security scheme integration."""

from typing import Annotated

from hawkapi import Depends, HawkAPI, HTTPBearer
from hawkapi.openapi.schema import generate_openapi
from hawkapi.security import APIKeyHeader, HTTPBasic, OAuth2PasswordBearer
from hawkapi.security.http_bearer import HTTPBearerCredentials


def test_bearer_security_in_openapi():
    app = HawkAPI(openapi_url=None)
    bearer = HTTPBearer()

    @app.get("/secure")
    async def secure(token: Annotated[HTTPBearerCredentials, Depends(bearer)]):
        return {"ok": True}

    spec = generate_openapi(app._collect_routes(), title="Test")
    operation = spec["paths"]["/secure"]["get"]
    assert "security" in operation
    assert {"HTTPBearer": []} in operation["security"]
    assert "securitySchemes" in spec["components"]
    assert spec["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }


def test_api_key_security_in_openapi():
    app = HawkAPI(openapi_url=None)
    api_key = APIKeyHeader(name="X-API-Key")

    @app.get("/secure")
    async def secure(key: Annotated[str, Depends(api_key)]):
        return {"ok": True}

    spec = generate_openapi(app._collect_routes(), title="Test")
    operation = spec["paths"]["/secure"]["get"]
    assert {"APIKeyHeader": []} in operation["security"]
    scheme = spec["components"]["securitySchemes"]["APIKeyHeader"]
    assert scheme["type"] == "apiKey"
    assert scheme["in"] == "header"
    assert scheme["name"] == "X-API-Key"


def test_basic_security_in_openapi():
    app = HawkAPI(openapi_url=None)
    basic = HTTPBasic()

    @app.get("/secure")
    async def secure(creds: Annotated[str, Depends(basic)]):
        return {"ok": True}

    spec = generate_openapi(app._collect_routes(), title="Test")
    assert spec["components"]["securitySchemes"]["HTTPBasic"] == {
        "type": "http",
        "scheme": "basic",
    }


def test_oauth2_security_in_openapi():
    app = HawkAPI(openapi_url=None)
    oauth2 = OAuth2PasswordBearer(token_url="/token")

    @app.get("/secure")
    async def secure(token: Annotated[str, Depends(oauth2)]):
        return {"ok": True}

    spec = generate_openapi(app._collect_routes(), title="Test")
    scheme = spec["components"]["securitySchemes"]["OAuth2PasswordBearer"]
    assert scheme["type"] == "oauth2"
    assert scheme["flows"]["password"]["tokenUrl"] == "/token"


def test_non_security_depends_not_in_openapi():
    app = HawkAPI(openapi_url=None)

    def get_db():
        return "db"

    @app.get("/data")
    async def data(db: Annotated[str, Depends(get_db)]):
        return {"db": db}

    spec = generate_openapi(app._collect_routes(), title="Test")
    operation = spec["paths"]["/data"]["get"]
    assert "security" not in operation
    assert "components" not in spec  # no schemas or security schemes


def test_no_security_schemes_when_none():
    app = HawkAPI(openapi_url=None)

    @app.get("/public")
    async def public():
        return {"ok": True}

    spec = generate_openapi(app._collect_routes(), title="Test")
    assert "components" not in spec
