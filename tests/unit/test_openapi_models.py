"""Tests for OpenAPI 3.1 model structs (instantiation coverage)."""

import msgspec

from hawkapi.openapi.models import (
    Components,
    Contact,
    ExternalDocs,
    Info,
    MediaType,
    OpenAPISpec,
    Operation,
    Parameter,
    PathItem,
    RequestBody,
    Response,
    Schema,
    Server,
    ServerVariable,
    Tag,
)


def test_contact():
    c = Contact(name="Test", url="https://test.com", email="t@t.com")
    assert c.name == "Test"


def test_info():
    i = Info(title="API", version="1.0", description="Desc", contact=Contact(name="Me"))
    assert i.title == "API"


def test_server_variable():
    sv = ServerVariable(default="v1", description="Version", enum=["v1", "v2"])
    assert sv.default == "v1"


def test_server():
    s = Server(url="/api", description="API", variables={"v": ServerVariable(default="v1")})
    assert s.url == "/api"


def test_external_docs():
    ed = ExternalDocs(url="https://docs.test", description="Docs")
    assert ed.url == "https://docs.test"


def test_schema():
    s = Schema(
        type="object",
        properties={"name": Schema(type="string")},
        required=["name"],
        min_length=1,
        max_length=100,
        pattern=r"\w+",
    )
    assert s.type == "object"


def test_schema_refs():
    s = Schema(
        all_of=[Schema(type="string")],
        any_of=[Schema(type="integer")],
        one_of=[Schema(type="boolean")],
        ref="#/components/schemas/Foo",
        nullable=True,
        additional_properties=True,
    )
    assert s.ref == "#/components/schemas/Foo"


def test_schema_with_items():
    s = Schema(type="array", items=Schema(type="string"))
    assert s.type == "array"


def test_media_type():
    mt = MediaType(schema=Schema(type="string"))
    assert mt.schema is not None


def test_request_body():
    rb = RequestBody(
        content={"application/json": MediaType()},
        required=True,
        description="Body",
    )
    assert rb.required is True


def test_parameter():
    p = Parameter(name="id", location="path", required=True, schema=Schema(type="integer"))
    assert p.name == "id"


def test_response():
    r = Response(description="OK", content={"application/json": MediaType()})
    assert r.description == "OK"


def test_operation():
    op = Operation(
        summary="Get",
        description="Get item",
        operation_id="getItem",
        tags=["items"],
        parameters=[Parameter(name="id")],
        request_body=RequestBody(),
        responses={"200": Response(description="OK")},
        deprecated=True,
    )
    assert op.deprecated is True


def test_path_item():
    pi = PathItem(
        get=Operation(summary="Get"),
        post=Operation(summary="Post"),
        put=Operation(summary="Put"),
        patch=Operation(summary="Patch"),
        delete=Operation(summary="Delete"),
        head=Operation(summary="Head"),
        options=Operation(summary="Options"),
        summary="Path",
        description="Desc",
    )
    assert pi.get is not None


def test_tag():
    t = Tag(name="users", description="User operations")
    assert t.name == "users"


def test_components():
    c = Components(schemas={"User": Schema(type="object")})
    assert "User" in c.schemas


def test_openapi_spec():
    spec = OpenAPISpec(
        openapi="3.1.0",
        info=Info(title="Test"),
        paths={"/users": PathItem(get=Operation(summary="List"))},
        servers=[Server(url="/")],
        tags=[Tag(name="users")],
        components=Components(),
    )
    assert spec.openapi == "3.1.0"


def test_openapi_spec_serializable():
    spec = OpenAPISpec(info=Info(title="Test"))
    data = msgspec.json.encode(spec)
    assert b"Test" in data
