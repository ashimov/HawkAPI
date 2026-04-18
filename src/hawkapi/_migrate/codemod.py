"""libcst-based codemod that rewrites FastAPI source into HawkAPI source.

The public entry point is :func:`migrate_file`. Walking a tree of files and
writing results back to disk is the responsibility of the CLI layer.

The transform set is intentionally small and conservative:

* Imports from ``fastapi`` / ``fastapi.responses`` / ``fastapi.middleware.*`` /
  ``fastapi.testclient`` are rewritten to their ``hawkapi`` equivalents.
* References to the ``FastAPI`` class are renamed to ``HawkAPI`` (the
  constructor call ``FastAPI(...)`` becomes ``HawkAPI(...)`` automatically).
* ``APIRouter`` is renamed to ``Router``.
* ``@app.on_event("startup" | "shutdown")`` becomes ``@app.on_startup`` /
  ``@app.on_shutdown``.
* When ``--convert-models`` is requested, ``class X(BaseModel):`` becomes
  ``class X(msgspec.Struct):`` and a ``import msgspec`` is added if missing.
  Models that define a ``@validator`` / ``@field_validator`` / ``@root_validator``
  are skipped with a warning.
* Path parameters that have an ``int`` / ``UUID`` annotation in the function
  signature are reported in warnings, suggesting the typed
  ``{name:int}`` syntax (we do **not** auto-rewrite — users may rely on the
  un-typed shape for OpenAPI compatibility).

The transforms are idempotent: running ``migrate_file`` twice on the same
source yields identical output and no extra warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import libcst as cst

# ---------------------------------------------------------------------------
# Module/symbol mapping
# ---------------------------------------------------------------------------

# fastapi.<module> -> hawkapi.<module>
_MODULE_MAP: dict[str, str] = {
    "fastapi": "hawkapi",
    "fastapi.responses": "hawkapi.responses",
    "fastapi.middleware": "hawkapi.middleware",
    "fastapi.middleware.cors": "hawkapi.middleware",
    "fastapi.middleware.gzip": "hawkapi.middleware",
    "fastapi.middleware.trustedhost": "hawkapi.middleware",
    "fastapi.testclient": "hawkapi.testing",
    "fastapi.exceptions": "hawkapi.exceptions",
    "fastapi.security": "hawkapi.security",
}

# Symbol renames (apply both at import time and at usage sites).
_SYMBOL_RENAMES: dict[str, str] = {
    "FastAPI": "HawkAPI",
    "APIRouter": "Router",
}

# Pydantic validator decorators that flag a class as "unsafe to convert".
_VALIDATOR_NAMES: frozenset[str] = frozenset(
    {
        "validator",
        "field_validator",
        "root_validator",
        "model_validator",
    }
)

# Type annotations that hint at a path-converter rewrite.
_TYPED_PATH_HINTS: dict[str, str] = {
    "int": "int",
    "float": "float",
    "UUID": "uuid",
    "uuid.UUID": "uuid",
    "str": "str",
}

# Path-segment placeholder regex: matches ``{name}`` but NOT ``{name:type}``.
_PATH_PARAM_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class _Context:
    """Per-file mutable state shared across visitors."""

    convert_models: bool = False
    warnings: list[str] = field(default_factory=list)
    needs_msgspec_import: bool = False
    has_msgspec_import: bool = False


# ---------------------------------------------------------------------------
# Helpers: dotted-name <-> string
# ---------------------------------------------------------------------------


def _dotted_name_to_str(node: cst.BaseExpression | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        left = _dotted_name_to_str(node.value)
        if not isinstance(node.attr, cst.Name) or left is None:
            return None
        return f"{left}.{node.attr.value}"
    return None


def _str_to_dotted_name(dotted: str) -> cst.Name | cst.Attribute:
    parts = dotted.split(".")
    node: cst.Name | cst.Attribute = cst.Name(parts[0])
    for part in parts[1:]:
        node = cst.Attribute(value=node, attr=cst.Name(part))
    return node


# ---------------------------------------------------------------------------
# Import rewriting
# ---------------------------------------------------------------------------


def _maybe_rename_import_alias(alias: cst.ImportAlias) -> cst.ImportAlias:
    """Rename ``FastAPI`` -> ``HawkAPI`` and ``APIRouter`` -> ``Router``."""
    name_node = alias.name
    if not isinstance(name_node, cst.Name):
        return alias
    new = _SYMBOL_RENAMES.get(name_node.value)
    if new is None:
        return alias
    # If the user aliased the import (``from fastapi import FastAPI as F``),
    # keep the local alias and just swap the source symbol.
    return alias.with_changes(name=cst.Name(new))


class _ImportRewriter(cst.CSTTransformer):
    """Rewrite ``from fastapi[.x] import ...`` and ``import fastapi`` lines."""

    def __init__(self, ctx: _Context) -> None:
        super().__init__()
        self.ctx = ctx

    # ``from fastapi[.x] import a, b as c``
    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.ImportFrom:
        module_name = _dotted_name_to_str(updated_node.module)
        if module_name is None:
            return updated_node

        if module_name not in _MODULE_MAP and not module_name.startswith("fastapi"):
            return updated_node

        new_module_str = _MODULE_MAP.get(module_name)
        if new_module_str is None and module_name.startswith("fastapi."):
            # Generic fallback: fastapi.<x> -> hawkapi.<x>.
            new_module_str = "hawkapi" + module_name[len("fastapi") :]

        if new_module_str is None:
            return updated_node

        new_module = _str_to_dotted_name(new_module_str)

        # Rename imported symbols (``FastAPI`` -> ``HawkAPI`` etc.).
        names = updated_node.names
        if isinstance(names, cst.ImportStar):
            return updated_node.with_changes(module=new_module)

        new_aliases = [_maybe_rename_import_alias(a) for a in names]
        return updated_node.with_changes(module=new_module, names=new_aliases)

    # ``import fastapi`` / ``import fastapi.responses`` / ``import fastapi as f``
    def leave_Import(self, original_node: cst.Import, updated_node: cst.Import) -> cst.Import:
        new_aliases: list[cst.ImportAlias] = []
        changed = False
        for alias in updated_node.names:
            name_str = _dotted_name_to_str(alias.name)
            if name_str is None or not (name_str == "fastapi" or name_str.startswith("fastapi.")):
                new_aliases.append(alias)
                continue
            new_str = _MODULE_MAP.get(name_str)
            if new_str is None and name_str.startswith("fastapi."):
                new_str = "hawkapi" + name_str[len("fastapi") :]
            if new_str is None:
                new_aliases.append(alias)
                continue
            changed = True
            new_aliases.append(alias.with_changes(name=_str_to_dotted_name(new_str)))
        if not changed:
            return updated_node
        return updated_node.with_changes(names=new_aliases)


# ---------------------------------------------------------------------------
# Symbol reference rewriting (FastAPI -> HawkAPI, APIRouter -> Router)
# ---------------------------------------------------------------------------


class _SymbolRewriter(cst.CSTTransformer):
    """Rename bare ``Name`` references to the renamed symbols.

    We avoid touching attribute access (``obj.FastAPI``) and string literals.
    """

    def __init__(self, ctx: _Context) -> None:
        super().__init__()
        self.ctx = ctx
        # Mark the ``attr`` half of every Attribute node so we don't rewrite it.
        self._skip_names: set[int] = set()

    def visit_Attribute(self, node: cst.Attribute) -> None:
        self._skip_names.add(id(node.attr))

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        if id(original_node) in self._skip_names:
            return updated_node
        new = _SYMBOL_RENAMES.get(updated_node.value)
        if new is None:
            return updated_node
        return updated_node.with_changes(value=new)


# ---------------------------------------------------------------------------
# Lifespan: ``@app.on_event("startup")`` -> ``@app.on_startup``
# ---------------------------------------------------------------------------


class _LifespanRewriter(cst.CSTTransformer):
    """Rewrite ``@app.on_event("startup" | "shutdown")`` decorators."""

    def leave_Decorator(
        self, original_node: cst.Decorator, updated_node: cst.Decorator
    ) -> cst.Decorator:
        deco = updated_node.decorator
        if not isinstance(deco, cst.Call):
            return updated_node
        func = deco.func
        if not isinstance(func, cst.Attribute) or not isinstance(func.attr, cst.Name):
            return updated_node
        if func.attr.value != "on_event":
            return updated_node
        if len(deco.args) != 1:
            return updated_node
        arg = deco.args[0].value
        if not isinstance(arg, cst.SimpleString):
            return updated_node
        event = arg.evaluated_value
        if event not in {"startup", "shutdown"}:
            return updated_node
        new_attr = cst.Attribute(value=func.value, attr=cst.Name(f"on_{event}"))
        return updated_node.with_changes(decorator=new_attr)


# ---------------------------------------------------------------------------
# Pydantic BaseModel -> msgspec.Struct
# ---------------------------------------------------------------------------


def _has_basemodel_base(node: cst.ClassDef) -> bool:
    for base in node.bases:
        val = base.value
        if isinstance(val, cst.Name) and val.value == "BaseModel":
            return True
        if (
            isinstance(val, cst.Attribute)
            and isinstance(val.attr, cst.Name)
            and val.attr.value == "BaseModel"
        ):
            return True
    return False


def _class_has_validator(node: cst.ClassDef) -> bool:
    for item in node.body.body:
        if not isinstance(item, cst.FunctionDef):
            continue
        for deco in item.decorators:
            d = deco.decorator
            name: str | None = None
            if isinstance(d, cst.Name):
                name = d.value
            elif isinstance(d, cst.Attribute) and isinstance(d.attr, cst.Name):
                name = d.attr.value
            elif isinstance(d, cst.Call):
                if isinstance(d.func, cst.Name):
                    name = d.func.value
                elif isinstance(d.func, cst.Attribute) and isinstance(d.func.attr, cst.Name):
                    name = d.func.attr.value
            if name in _VALIDATOR_NAMES:
                return True
    return False


def _replace_basemodel_base(base: cst.Arg) -> cst.Arg:
    val = base.value
    if isinstance(val, cst.Name) and val.value == "BaseModel":
        return base.with_changes(
            value=cst.Attribute(value=cst.Name("msgspec"), attr=cst.Name("Struct"))
        )
    if (
        isinstance(val, cst.Attribute)
        and isinstance(val.attr, cst.Name)
        and val.attr.value == "BaseModel"
    ):
        return base.with_changes(
            value=cst.Attribute(value=cst.Name("msgspec"), attr=cst.Name("Struct"))
        )
    return base


class _ModelRewriter(cst.CSTTransformer):
    """Rewrite ``class X(BaseModel)`` into ``class X(msgspec.Struct)``.

    Skips classes that define ``@validator`` / ``@field_validator`` /
    ``@root_validator`` / ``@model_validator`` decorators — those rely on
    Pydantic semantics and need manual review.
    """

    def __init__(self, ctx: _Context) -> None:
        super().__init__()
        self.ctx = ctx

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        if not _has_basemodel_base(updated_node):
            return updated_node

        if _class_has_validator(updated_node):
            self.ctx.warnings.append(
                f"class {updated_node.name.value}: contains a Pydantic validator decorator; "
                "skipped — convert manually to a msgspec __post_init__ or msgspec.Meta()."
            )
            return updated_node

        new_bases = [_replace_basemodel_base(b) for b in updated_node.bases]
        self.ctx.needs_msgspec_import = True
        return updated_node.with_changes(bases=new_bases)


# ---------------------------------------------------------------------------
# Path-parameter typing hints (warning only)
# ---------------------------------------------------------------------------


def _route_path_from_decorator(deco: cst.Decorator, verbs: set[str]) -> str | None:
    d = deco.decorator
    if not isinstance(d, cst.Call):
        return None
    func = d.func
    if isinstance(func, cst.Attribute) and isinstance(func.attr, cst.Name):
        if func.attr.value not in verbs:
            return None
    else:
        return None
    if not d.args:
        return None
    first = d.args[0].value
    if isinstance(first, cst.SimpleString):
        value = first.evaluated_value
        return value if isinstance(value, str) else None
    return None


def _annotation_str(annotation: cst.Annotation | None) -> str | None:
    if annotation is None:
        return None
    ann = annotation.annotation
    if isinstance(ann, cst.Name):
        return ann.value
    if (
        isinstance(ann, cst.Attribute)
        and isinstance(ann.attr, cst.Name)
        and isinstance(ann.value, cst.Name)
    ):
        return f"{ann.value.value}.{ann.attr.value}"
    return None


class _PathParamHintCollector(cst.CSTVisitor):
    """Collect warnings about path params that could use typed converters."""

    def __init__(self, ctx: _Context) -> None:
        super().__init__()
        self.ctx = ctx
        self._verbs = {"get", "post", "put", "patch", "delete", "head", "options", "route"}

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        for deco in node.decorators:
            path = _route_path_from_decorator(deco, self._verbs)
            if path is None:
                continue
            params = {p.name.value: _annotation_str(p.annotation) for p in node.params.params}
            for match in _PATH_PARAM_RE.finditer(path):
                name = match.group(1)
                ann = params.get(name)
                if ann is None:
                    continue
                converter = _TYPED_PATH_HINTS.get(ann)
                if converter is None or converter == "str":
                    continue
                self.ctx.warnings.append(
                    f"function {node.name.value}: path '{path}' has parameter "
                    f"'{name}: {ann}'. Consider the typed syntax "
                    f"'{{{name}:{converter}}}' for automatic coercion."
                )


# ---------------------------------------------------------------------------
# msgspec import insertion
# ---------------------------------------------------------------------------


class _MsgspecImportScanner(cst.CSTVisitor):
    """Detect whether the module already imports ``msgspec``."""

    def __init__(self, ctx: _Context) -> None:
        super().__init__()
        self.ctx = ctx

    def visit_Import(self, node: cst.Import) -> None:
        for alias in node.names:
            name = _dotted_name_to_str(alias.name)
            if name == "msgspec" or (name is not None and name.startswith("msgspec.")):
                self.ctx.has_msgspec_import = True

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        name = _dotted_name_to_str(node.module)
        if name == "msgspec" or (name is not None and name.startswith("msgspec.")):
            self.ctx.has_msgspec_import = True


def _insert_msgspec_import(module: cst.Module) -> cst.Module:
    """Insert ``import msgspec`` after the last existing top-level import."""
    new_body: list[cst.BaseStatement] = list(module.body)
    insert_at = 0
    for idx, stmt in enumerate(new_body):
        if isinstance(stmt, cst.SimpleStatementLine) and any(
            isinstance(s, cst.Import | cst.ImportFrom) for s in stmt.body
        ):
            insert_at = idx + 1
    import_stmt = cst.SimpleStatementLine(
        body=[cst.Import(names=[cst.ImportAlias(cst.Name("msgspec"))])]
    )
    new_body.insert(insert_at, import_stmt)
    return module.with_changes(body=new_body)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def migrate_file(source: str, *, convert_models: bool = False) -> tuple[str, list[str]]:
    """Apply all transforms to a source file.

    Parameters
    ----------
    source:
        Original ``.py`` source text.
    convert_models:
        When ``True``, also rewrite ``class X(BaseModel)`` into
        ``class X(msgspec.Struct)`` and inject ``import msgspec`` if needed.

    Returns
    -------
    tuple[str, list[str]]
        ``(new_source, warnings)``. ``new_source`` equals ``source`` when no
        transform applied. ``warnings`` is a list of human-readable hints
        (suggested typed path params, skipped validator classes, etc.).
    """
    if not source.strip():
        return source, []

    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        return source, [f"parse error: {exc}; file left unchanged."]

    ctx = _Context(convert_models=convert_models)

    # Order matters:
    # 1. detect existing msgspec import (so we don't add a duplicate later).
    module.visit(_MsgspecImportScanner(ctx))
    # 2. rewrite imports first.
    module = cst.ensure_type(module.visit(_ImportRewriter(ctx)), cst.Module)
    # 3. rewrite bare references (FastAPI() -> HawkAPI(), APIRouter() -> Router()).
    module = cst.ensure_type(module.visit(_SymbolRewriter(ctx)), cst.Module)
    # 4. lifespan decorators.
    module = cst.ensure_type(module.visit(_LifespanRewriter()), cst.Module)
    # 5. optional pydantic -> msgspec.
    if convert_models:
        module = cst.ensure_type(module.visit(_ModelRewriter(ctx)), cst.Module)
        if ctx.needs_msgspec_import and not ctx.has_msgspec_import:
            module = _insert_msgspec_import(module)
    # 6. collect path-param hints (warning only).
    module.visit(_PathParamHintCollector(ctx))

    return module.code, ctx.warnings
