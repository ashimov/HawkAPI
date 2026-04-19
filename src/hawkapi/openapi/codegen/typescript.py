"""ClientIR → single-file TypeScript client renderer."""

from __future__ import annotations

import re

from hawkapi.openapi.codegen.ir import ClientIR, OperationIR, SchemaIR


def _py_type_to_ts(s: str) -> str:
    """Convert a Python-dialect type string to TypeScript.

    Handles: int/float→number, str→string, bool→boolean, None→null,
    list[X]→X[], dict[str, X]→Record<string, X>, X | Y→X | Y,
    Any→unknown, struct/enum identifiers pass through unchanged.
    """
    s = s.strip()

    # Any
    if s == "Any":
        return "unknown"

    # None
    if s == "None":
        return "null"

    # Primitives
    if s in ("int", "float"):
        return "number"
    if s == "str":
        return "string"
    if s == "bool":
        return "boolean"

    # list[X] → X[]
    m = re.fullmatch(r"list\[(.+)\]", s)
    if m:
        inner = _py_type_to_ts(m.group(1))
        return f"{inner}[]"

    # dict[str, X] → Record<string, X>
    m = re.fullmatch(r"dict\[str,\s*(.+)\]", s)
    if m:
        val = _py_type_to_ts(m.group(1))
        return f"Record<string, {val}>"

    # X | Y  (union — split on top-level |)
    if "|" in s:
        parts = [p.strip() for p in s.split("|")]
        return " | ".join(_py_type_to_ts(p) for p in parts)

    # Identifier (struct name, enum name) — pass through
    return s


def _to_camel_case(snake: str) -> str:
    """Convert ``snake_case`` or ``kebab-case`` to ``lowerCamelCase``."""
    parts = re.split(r"[_\-]+", snake)
    if not parts:
        return snake
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _render_ts_interface(schema: SchemaIR) -> str:
    """Render an ``export interface X { ... }`` block."""
    lines: list[str] = [f"export interface {schema.name} {{"]
    for f in schema.fields:
        ts_type = _py_type_to_ts(f.type_str)
        optional = "?" if not f.required else ""
        if f.description:
            lines.append(f"  /** {f.description} */")
        lines.append(f"  {f.name}{optional}: {ts_type};")
    lines.append("}")
    return "\n".join(lines)


def _render_ts_alias(schema: SchemaIR) -> str:
    """Render ``export type X = Y[]`` or similar."""
    ts_type = _py_type_to_ts(schema.alias_of or "unknown")
    return f"export type {schema.name} = {ts_type};"


def _render_ts_enum(schema: SchemaIR) -> str:
    """Render ``export type X = "a" | "b";``."""
    values = " | ".join(repr(v) for v in schema.enum_values)
    return f"export type {schema.name} = {values};"


def _render_ts_method(op: OperationIR) -> str:
    """Render a single async method on the Client class."""
    lines: list[str] = []
    method_name = _to_camel_case(op.operation_id)

    # Build params interface inline
    param_entries: list[str] = []
    for p in op.path_params:
        ts_type = _py_type_to_ts(p.type_str)
        param_entries.append(f"{p.name}: {ts_type}")
    for p in op.query_params:
        ts_type = _py_type_to_ts(p.type_str)
        opt = "" if p.required else "?"
        param_entries.append(f"{p.name}{opt}: {ts_type}")
    for p in op.header_params:
        ts_type = _py_type_to_ts(p.type_str)
        opt = "" if p.required else "?"
        param_entries.append(f"{p.name}{opt}: {ts_type}")

    if op.body_type:
        ts_body = _py_type_to_ts(op.body_type)
        param_entries.append(f"body?: {ts_body}")

    params_str = ("params?: { " + "; ".join(param_entries) + " }") if param_entries else ""

    return_ts = _py_type_to_ts(op.response_type) if op.response_type else "void"
    promise_type = f"Promise<{return_ts}>"

    if params_str:
        lines.append(f"  async {method_name}({params_str}): {promise_type} {{")
    else:
        lines.append(f"  async {method_name}(): {promise_type} {{")

    # Build URL — replace {param} with template literal ${params?.param}
    ts_path = op.path
    for p in op.path_params:
        ts_path = ts_path.replace(f"{{{p.name}}}", f"${{params?.{p.name}}}")

    lines.append(f"    const url = new URL(`${{this.baseUrl}}{ts_path}`);")

    # Query params
    for p in op.query_params:
        lines.append(f"    if (params?.{p.name} !== undefined) {{")
        lines.append(f'      url.searchParams.set("{p.name}", String(params.{p.name}));')
        lines.append("    }")

    # Headers
    lines.append("    const headers: Record<string, string> = { ...this.headers };")
    for p in op.header_params:
        lines.append(f"    if (params?.{p.name} !== undefined) {{")
        lines.append(f'      headers["{p.name}"] = String(params.{p.name});')
        lines.append("    }")

    # Fetch options
    if op.body_type:
        lines.append('    headers["Content-Type"] = "application/json";')
        lines.append("    const resp = await this.fetchImpl(url.toString(), {")
        lines.append(f'      method: "{op.method.upper()}",')
        lines.append("      headers,")
        lines.append(
            "      body: params?.body !== undefined ? JSON.stringify(params.body) : undefined,"
        )
        lines.append("    });")
    else:
        lines.append("    const resp = await this.fetchImpl(url.toString(), {")
        lines.append(f'      method: "{op.method.upper()}",')
        lines.append("      headers,")
        lines.append("    });")

    # Error check
    lines.append("    if (!resp.ok) {")
    lines.append("      throw new ApiError(resp.status, await resp.json().catch(() => null));")
    lines.append("    }")

    # Return
    if op.response_type:
        lines.append(f"    return resp.json() as Promise<{return_ts}>;")
    else:
        lines.append("    return;")

    lines.append("  }")
    return "\n".join(lines)


def generate_typescript_client(ir: ClientIR) -> str:
    """Render *ir* as a single-file TypeScript client.

    Parameters
    ----------
    ir:
        Populated :class:`~hawkapi.openapi.codegen.ir.ClientIR`.

    Returns
    -------
    str
        Complete TypeScript source code for ``client.ts`` (ESM-compatible,
        native fetch, TS 4.5+).
    """
    parts: list[str] = []

    # Header comment
    parts.append(
        f"/** Generated HawkAPI client for {ir.title} v{ir.version} — do not edit by hand. */"
    )
    parts.append("")

    # Schemas
    for schema in ir.schemas:
        if schema.kind == "struct":
            parts.append(_render_ts_interface(schema))
        elif schema.kind == "alias":
            parts.append(_render_ts_alias(schema))
        elif schema.kind == "enum":
            parts.append(_render_ts_enum(schema))
        parts.append("")

    # ApiError
    parts.append("export class ApiError extends Error {")
    parts.append("  constructor(public status: number, public detail: unknown) {")
    parts.append("    super(`HTTP ${status}: ${JSON.stringify(detail)}`);")
    parts.append('    this.name = "ApiError";')
    parts.append("  }")
    parts.append("}")
    parts.append("")

    # ClientOptions interface
    parts.append("export interface ClientOptions {")
    parts.append("  baseUrl: string;")
    parts.append("  headers?: Record<string, string>;")
    parts.append("  fetch?: typeof fetch;")
    parts.append("}")
    parts.append("")

    # Client class
    parts.append(f"/** Async HTTP client for {ir.title} v{ir.version}. */")
    parts.append("export class Client {")
    parts.append("  readonly baseUrl: string;")
    parts.append("  readonly headers: Record<string, string>;")
    parts.append("  private readonly fetchImpl: typeof fetch;")
    parts.append("")
    parts.append("  constructor(options: ClientOptions) {")
    parts.append('    this.baseUrl = options.baseUrl.replace(/\\/+$/, "");')
    parts.append("    this.headers = options.headers ?? {};")
    parts.append("    this.fetchImpl = options.fetch ?? globalThis.fetch;")
    parts.append("  }")
    parts.append("")

    # Operations
    for op in ir.operations:
        parts.append(_render_ts_method(op))
        parts.append("")

    parts.append("}")
    parts.append("")

    return "\n".join(parts)
