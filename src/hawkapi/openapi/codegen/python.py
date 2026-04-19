"""ClientIR → single-file Python client renderer."""

from __future__ import annotations

import ast
from typing import Any

from hawkapi.openapi.codegen.ir import (
    SENTINEL,
    ClientIR,
    FieldIR,
    OperationIR,
    SchemaIR,
)


def _py_default_repr(default: Any) -> str:
    """Return a safe Python literal string for a default value."""
    if default is None:
        return "None"
    if isinstance(default, bool):
        return "True" if default else "False"
    if isinstance(default, (int, float)):
        return repr(default)
    if isinstance(default, str):
        return repr(default)
    return "None"


def _render_field_default(field: FieldIR) -> str:
    """Return the default expression for a struct field annotation."""
    if field.default is SENTINEL:
        return ""
    return f" = {_py_default_repr(field.default)}"


def _render_struct(schema: SchemaIR) -> str:
    """Render a ``msgspec.Struct`` class for a struct SchemaIR."""
    lines: list[str] = [f"class {schema.name}(msgspec.Struct):"]
    if not schema.fields:
        lines.append("    pass")
        return "\n".join(lines)

    for f in schema.fields:
        default_expr = _render_field_default(f)
        annotation = f"    {f.name}: {f.type_str}{default_expr}"
        if f.description:
            lines.append(f"    # {f.description}")
        lines.append(annotation)
    return "\n".join(lines)


def _render_alias(schema: SchemaIR) -> str:
    """Render a module-level type alias."""
    return f"{schema.name} = {schema.alias_of}"


def _render_enum(schema: SchemaIR) -> str:
    """Render a ``Literal[...]`` type alias for an enum SchemaIR."""
    values = ", ".join(repr(v) for v in schema.enum_values)
    return f"{schema.name} = Literal[{values}]"


def _path_to_fstring(path: str) -> str:
    """Convert ``/items/{id}`` → ``f\"{self._base_url}/items/{id}\"``."""
    return f'f"{{self._base_url}}{path}"'


def _render_operation(op: OperationIR) -> str:
    """Render a single async method for an operation."""
    lines: list[str] = []

    # Build signature parts
    sig_parts: list[str] = ["self"]

    # Positional path params
    for p in op.path_params:
        sig_parts.append(f"{p.name}: {p.type_str}")

    # Keyword-only params after *
    kw_parts: list[str] = []
    for p in op.query_params:
        if p.required:
            kw_parts.append(f"{p.name}: {p.type_str}")
        else:
            kw_parts.append(f"{p.name}: {p.type_str} | None = None")
    for p in op.header_params:
        if p.required:
            kw_parts.append(f"{p.name}: {p.type_str}")
        else:
            kw_parts.append(f"{p.name}: {p.type_str} | None = None")

    if op.body_type:
        kw_parts.append(f"body: {op.body_type} | None = None")

    if kw_parts:
        sig_parts.append("*")
        sig_parts.extend(kw_parts)

    return_type = op.response_type if op.response_type else "None"
    sig = ", ".join(sig_parts)

    lines.append(f"    async def {op.operation_id}({sig}) -> {return_type}:")

    # Docstring
    if op.summary or op.description:
        doc = op.summary or op.description or ""
        lines.append(f'        """{doc}"""')

    # URL
    url_expr = _path_to_fstring(op.path)
    lines.append(f"        url = {url_expr}")

    # Query params dict
    if op.query_params:
        lines.append("        params: dict[str, Any] = {}")
        for p in op.query_params:
            if p.required:
                lines.append(f'        params["{p.name}"] = {p.name}')
            else:
                lines.append(f"        if {p.name} is not None:")
                lines.append(f'            params["{p.name}"] = {p.name}')
    else:
        lines.append("        params: dict[str, Any] = {}")

    # Headers
    if op.header_params:
        lines.append("        extra_headers: dict[str, str] = {}")
        for p in op.header_params:
            if p.required:
                lines.append(f'        extra_headers["{p.name}"] = {p.name}')
            else:
                lines.append(f"        if {p.name} is not None:")
                lines.append(f'            extra_headers["{p.name}"] = str({p.name})')
        lines.append("        merged_headers = {**self._headers, **extra_headers}")
    else:
        lines.append("        merged_headers = self._headers")

    # Body + HTTP call
    if op.body_type:
        lines.append("        content = msgspec.json.encode(body) if body is not None else None")
        lines.append(
            f"        r = await self._client.{op.method}("
            "url, params=params, headers=merged_headers, content=content)"
        )
    else:
        lines.append(
            f"        r = await self._client.{op.method}("
            "url, params=params, headers=merged_headers)"
        )

    # Error check
    lines.append("        if r.status_code >= 400:")
    lines.append("            raise ApiError(r.status_code, r.json())")

    # Return
    if op.response_type:
        lines.append(f"        return msgspec.convert(r.json(), type={return_type})")
    else:
        lines.append("        return None")

    return "\n".join(lines)


def generate_python_client(ir: ClientIR) -> str:
    """Render *ir* as a single-file Python async client.

    Parameters
    ----------
    ir:
        Populated :class:`~hawkapi.openapi.codegen.ir.ClientIR`.

    Returns
    -------
    str
        Complete Python source code for ``client.py``.
        The output is validated with :func:`ast.parse` before returning.
    """
    parts: list[str] = []

    # File header docstring
    parts.append(
        f'"""Generated HawkAPI client for {ir.title} v{ir.version} — do not edit by hand."""'
    )
    parts.append("")
    parts.append("from __future__ import annotations")
    parts.append("")
    parts.append("from typing import Any, Literal")
    parts.append("")
    parts.append("import httpx")
    parts.append("import msgspec")
    parts.append("")
    parts.append("")

    # ApiError
    parts.append("class ApiError(Exception):")
    parts.append('    """Raised when the server returns a 4xx or 5xx response."""')
    parts.append("")
    parts.append("    def __init__(self, status_code: int, detail: Any) -> None:")
    parts.append('        super().__init__(f"HTTP {status_code}: {detail}")')
    parts.append("        self.status_code = status_code")
    parts.append("        self.detail = detail")
    parts.append("")
    parts.append("")

    # Schemas
    for schema in ir.schemas:
        if schema.kind == "struct":
            parts.append(_render_struct(schema))
        elif schema.kind == "alias":
            parts.append(_render_alias(schema))
        elif schema.kind == "enum":
            parts.append(_render_enum(schema))
        parts.append("")
        parts.append("")

    # Client class
    parts.append("class Client:")
    parts.append(f'    """Async HTTP client for {ir.title} v{ir.version}."""')
    parts.append("")

    # __init__
    parts.append(
        "    def __init__("
        "self, base_url: str, *, "
        "headers: dict[str, str] | None = None, "
        "client: httpx.AsyncClient | None = None"
        ") -> None:"
    )
    parts.append('        self._base_url = base_url.rstrip("/")')
    parts.append("        self._headers: dict[str, str] = dict(headers) if headers else {}")
    parts.append("        self._owned = client is None")
    parts.append("        self._client = client or httpx.AsyncClient()")
    parts.append("")

    # aclose
    parts.append("    async def aclose(self) -> None:")
    parts.append('        """Close the underlying HTTP client if owned."""')
    parts.append("        if self._owned:")
    parts.append("            await self._client.aclose()")
    parts.append("")

    # async context manager
    parts.append("    async def __aenter__(self) -> Client:")
    parts.append("        return self")
    parts.append("")
    parts.append("    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:")
    parts.append("        await self.aclose()")
    parts.append("")

    # Operations
    for op in ir.operations:
        parts.append(_render_operation(op))
        parts.append("")

    source = "\n".join(parts)

    # Validate — raises SyntaxError on bad output
    ast.parse(source)

    return source
