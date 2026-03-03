"""OpenAPI 3.1 specification models as msgspec Structs."""

from __future__ import annotations

from typing import Any

import msgspec


class Contact(msgspec.Struct, omit_defaults=True):
    """OpenAPI Contact Object."""

    name: str | None = None
    url: str | None = None
    email: str | None = None


class Info(msgspec.Struct, omit_defaults=True):
    """OpenAPI Info Object."""

    title: str = "HawkAPI"
    version: str = "0.1.0"
    description: str | None = None
    contact: Contact | None = None


class ServerVariable(msgspec.Struct, omit_defaults=True):
    """OpenAPI Server Variable Object."""

    default: str = ""
    description: str | None = None
    enum: list[str] | None = None


class Server(msgspec.Struct, omit_defaults=True):
    url: str = "/"
    description: str | None = None
    variables: dict[str, ServerVariable] | None = None


class ExternalDocs(msgspec.Struct, omit_defaults=True):
    url: str = ""
    description: str | None = None


class Schema(msgspec.Struct, omit_defaults=True):
    type: str | None = None
    format: str | None = None
    title: str | None = None
    description: str | None = None
    default: Any = None
    enum: list[Any] | None = None
    items: Schema | dict[str, Any] | None = None
    properties: dict[str, Schema | dict[str, Any]] | None = None
    required: list[str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    all_of: list[Schema | dict[str, Any]] | None = msgspec.field(name="allOf", default=None)
    any_of: list[Schema | dict[str, Any]] | None = msgspec.field(name="anyOf", default=None)
    one_of: list[Schema | dict[str, Any]] | None = msgspec.field(name="oneOf", default=None)
    ref: str | None = msgspec.field(name="$ref", default=None)
    nullable: bool | None = None
    additional_properties: bool | Schema | dict[str, Any] | None = msgspec.field(
        name="additionalProperties", default=None
    )


class MediaType(msgspec.Struct, omit_defaults=True):
    schema: Schema | dict[str, Any] | None = None


class RequestBody(msgspec.Struct, omit_defaults=True):
    content: dict[str, MediaType] | None = None
    required: bool = True
    description: str | None = None


class Parameter(msgspec.Struct, omit_defaults=True):
    name: str = ""
    location: str = msgspec.field(name="in", default="query")
    required: bool = False
    schema: Schema | dict[str, Any] | None = None
    description: str | None = None


class Response(msgspec.Struct, omit_defaults=True):
    description: str = ""
    content: dict[str, MediaType] | None = None


class Operation(msgspec.Struct, omit_defaults=True):
    summary: str | None = None
    description: str | None = None
    operation_id: str | None = msgspec.field(name="operationId", default=None)
    tags: list[str] | None = None
    parameters: list[Parameter] | None = None
    request_body: RequestBody | None = msgspec.field(name="requestBody", default=None)
    responses: dict[str, Response] | None = None
    deprecated: bool | None = None
    security: list[dict[str, list[str]]] | None = None


class PathItem(msgspec.Struct, omit_defaults=True):
    get: Operation | None = None
    post: Operation | None = None
    put: Operation | None = None
    patch: Operation | None = None
    delete: Operation | None = None
    head: Operation | None = None
    options: Operation | None = None
    summary: str | None = None
    description: str | None = None


class Tag(msgspec.Struct, omit_defaults=True):
    name: str = ""
    description: str | None = None


class Components(msgspec.Struct, omit_defaults=True):
    schemas: dict[str, Schema | dict[str, Any]] | None = None
    security_schemes: dict[str, dict[str, Any]] | None = msgspec.field(
        name="securitySchemes", default=None
    )


class OpenAPISpec(msgspec.Struct, omit_defaults=True):
    openapi: str = "3.1.0"
    info: Info = msgspec.field(default_factory=Info)
    paths: dict[str, PathItem] = msgspec.field(default_factory=lambda: {})
    servers: list[Server] | None = None
    tags: list[Tag] | None = None
    components: Components | None = None
