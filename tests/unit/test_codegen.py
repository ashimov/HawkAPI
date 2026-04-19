"""Tests for OpenAPI client codegen."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from hawkapi.openapi.codegen import (
    build_client_ir,
    generate_python_client,
    generate_typescript_client,
)

# ---------------------------------------------------------------------------
# Shared fixture spec
# ---------------------------------------------------------------------------

MINIMAL_SPEC: dict = {
    "openapi": "3.1.0",
    "info": {"title": "Test", "version": "0.1.0"},
    "paths": {
        "/items": {
            "get": {
                "operationId": "list_items",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "schema": {"type": "string"},
                        "required": False,
                    },
                ],
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Item"},
                                }
                            }
                        },
                    }
                },
            },
            "post": {
                "operationId": "create_item",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Item"}}
                    },
                },
                "responses": {
                    "201": {
                        "description": "created",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Item"}}
                        },
                    }
                },
            },
        },
        "/items/{id}": {
            "get": {
                "operationId": "get_item",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "schema": {"type": "integer"},
                        "required": True,
                    },
                ],
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Item"}}
                        },
                    }
                },
            },
        },
    },
    "components": {
        "schemas": {
            "Item": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["id", "name"],
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


def test_parser_minimal_spec() -> None:
    """Single endpoint no params no body → 1 operation, 0 schemas."""
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Tiny", "version": "0.0.1"},
        "paths": {
            "/ping": {
                "get": {
                    "operationId": "ping",
                    "responses": {"200": {"description": "pong"}},
                }
            }
        },
    }
    ir = build_client_ir(spec)
    assert ir.title == "Tiny"
    assert ir.version == "0.0.1"
    assert len(ir.operations) == 1
    assert len(ir.schemas) == 0
    op = ir.operations[0]
    assert op.operation_id == "ping"
    assert op.method == "get"
    assert op.path == "/ping"


def test_parser_path_param() -> None:
    """/items/{id} with id:int → path_params has one required int ParamIR."""
    ir = build_client_ir(MINIMAL_SPEC)
    get_item = next(op for op in ir.operations if op.operation_id == "get_item")
    assert len(get_item.path_params) == 1
    p = get_item.path_params[0]
    assert p.name == "id"
    assert p.type_str == "int"
    assert p.required is True


def test_parser_query_param_optional() -> None:
    """?q= optional query param → query_params has one optional ParamIR."""
    ir = build_client_ir(MINIMAL_SPEC)
    list_items = next(op for op in ir.operations if op.operation_id == "list_items")
    assert len(list_items.query_params) == 1
    q = list_items.query_params[0]
    assert q.name == "q"
    assert q.required is False
    assert q.default is None


def test_parser_body_ref() -> None:
    """POST with request body $ref Item → body_type='Item'."""
    ir = build_client_ir(MINIMAL_SPEC)
    create_item = next(op for op in ir.operations if op.operation_id == "create_item")
    assert create_item.body_type == "Item"


def test_parser_response_ref() -> None:
    """200 response $ref Item → response_type='Item'."""
    ir = build_client_ir(MINIMAL_SPEC)
    get_item = next(op for op in ir.operations if op.operation_id == "get_item")
    assert get_item.response_type == "Item"


def test_parser_schema_struct() -> None:
    """Item with id:int, name:str, description:str? → struct with correct required flags."""
    ir = build_client_ir(MINIMAL_SPEC)
    item_schema = next(s for s in ir.schemas if s.name == "Item")
    assert item_schema.kind == "struct"
    fields_by_name = {f.name: f for f in item_schema.fields}
    assert fields_by_name["id"].required is True
    assert fields_by_name["id"].type_str == "int"
    assert fields_by_name["name"].required is True
    assert fields_by_name["name"].type_str == "str"
    assert fields_by_name["description"].required is False
    assert fields_by_name["description"].default is None


def test_parser_schema_array_alias() -> None:
    """Schema type:array items:$ref → kind='alias', alias_of='list[Item]'."""
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "T", "version": "0"},
        "paths": {},
        "components": {
            "schemas": {
                "ItemList": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Item"},
                },
                "Item": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                    "required": ["id"],
                },
            }
        },
    }
    ir = build_client_ir(spec)
    item_list = next(s for s in ir.schemas if s.name == "ItemList")
    assert item_list.kind == "alias"
    assert item_list.alias_of == "list[Item]"


def test_parser_operation_id_fallback() -> None:
    """Missing operationId → auto-generated name containing method and path segments."""
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "T", "version": "0"},
        "paths": {
            "/foo/bar": {
                "get": {
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    ir = build_client_ir(spec)
    assert len(ir.operations) == 1
    op = ir.operations[0]
    assert op.operation_id.startswith("get_")
    assert "foo" in op.operation_id
    assert "bar" in op.operation_id


# ---------------------------------------------------------------------------
# Python renderer tests
# ---------------------------------------------------------------------------


def test_python_renderer_is_valid_python() -> None:
    """ast.parse the whole generated output — must not raise SyntaxError."""
    ir = build_client_ir(MINIMAL_SPEC)
    source = generate_python_client(ir)
    tree = ast.parse(source)
    assert tree is not None


def test_python_renderer_struct_emitted() -> None:
    """Generated code contains 'class Item(msgspec.Struct)'."""
    ir = build_client_ir(MINIMAL_SPEC)
    source = generate_python_client(ir)
    assert "class Item(msgspec.Struct):" in source


def test_python_renderer_path_param_positional() -> None:
    """get_item method signature has positional 'id: int'."""
    ir = build_client_ir(MINIMAL_SPEC)
    source = generate_python_client(ir)
    assert "async def get_item(self, id: int)" in source


def test_python_renderer_optional_query_skipped_when_none() -> None:
    """Generated method body has 'if q is not None:' guard for optional query param."""
    ir = build_client_ir(MINIMAL_SPEC)
    source = generate_python_client(ir)
    assert "if q is not None:" in source


# ---------------------------------------------------------------------------
# TypeScript renderer tests
# ---------------------------------------------------------------------------


def test_typescript_renderer_interface_emitted() -> None:
    """Generated TS contains 'export interface Item {'."""
    ir = build_client_ir(MINIMAL_SPEC)
    source = generate_typescript_client(ir)
    assert "export interface Item {" in source


def test_typescript_renderer_method_emitted() -> None:
    """Generated TS contains a method that uses baseUrl."""
    ir = build_client_ir(MINIMAL_SPEC)
    source = generate_typescript_client(ir)
    assert "this.baseUrl" in source


def test_typescript_renderer_apierror_class() -> None:
    """Generated TS contains 'export class ApiError'."""
    ir = build_client_ir(MINIMAL_SPEC)
    source = generate_typescript_client(ir)
    assert "export class ApiError" in source


def test_typescript_renderer_client_class() -> None:
    """Generated TS contains 'export class Client'."""
    ir = build_client_ir(MINIMAL_SPEC)
    source = generate_typescript_client(ir)
    assert "export class Client" in source


# ---------------------------------------------------------------------------
# CLI smoke tests (subprocess)
# ---------------------------------------------------------------------------


def test_cli_gen_python_smoke(tmp_path: Path) -> None:
    """CLI gen-client python produces a syntactically valid client.py."""
    spec_file = tmp_path / "openapi.json"
    spec_file.write_text(json.dumps(MINIMAL_SPEC), encoding="utf-8")
    out_dir = tmp_path / "pyclient"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hawkapi.cli",
            "gen-client",
            "python",
            "--spec",
            str(spec_file),
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    client_py = out_dir / "client.py"
    assert client_py.exists()
    ast.parse(client_py.read_text(encoding="utf-8"))


def test_cli_gen_typescript_smoke(tmp_path: Path) -> None:
    """CLI gen-client typescript produces client.ts containing 'export class Client'."""
    spec_file = tmp_path / "openapi.json"
    spec_file.write_text(json.dumps(MINIMAL_SPEC), encoding="utf-8")
    out_dir = tmp_path / "tsclient"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hawkapi.cli",
            "gen-client",
            "typescript",
            "--spec",
            str(spec_file),
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    client_ts = out_dir / "client.ts"
    assert client_ts.exists()
    assert "export class Client" in client_ts.read_text(encoding="utf-8")
