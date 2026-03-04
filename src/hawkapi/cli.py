"""HawkAPI CLI — development server launcher and API diff tool."""

from __future__ import annotations

import argparse
import importlib
import sys
from types import ModuleType
from typing import Any

from hawkapi.openapi.breaking_changes import Change, detect_breaking_changes, format_report
from hawkapi.openapi.schema import generate_openapi


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``hawkapi`` command."""
    parser = argparse.ArgumentParser(
        prog="hawkapi",
        description="HawkAPI development tools",
    )
    subparsers = parser.add_subparsers(dest="command")

    # `hawkapi dev` subcommand
    dev_parser = subparsers.add_parser("dev", help="Start development server")
    dev_parser.add_argument(
        "app",
        help="Application to run (module:attribute format, e.g. main:app)",
    )
    dev_parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    dev_parser.add_argument("--port", type=int, default=8000, help="Bind port")
    dev_parser.add_argument(
        "--reload",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable auto-reload",
    )

    # `hawkapi diff` subcommand
    diff_parser = subparsers.add_parser(
        "diff", help="Detect breaking API changes between two app versions"
    )
    diff_parser.add_argument("old", help="Old app reference (module:attr, e.g. myapp.main:app)")
    diff_parser.add_argument("new", help="New app reference (module:attr, e.g. myapp.main:app)")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "dev":
        _run_dev(args)
    elif args.command == "diff":
        sys.exit(_run_diff(args))


def _run_dev(args: argparse.Namespace) -> None:
    """Run the development server using uvicorn."""
    try:
        import uvicorn
    except ImportError:
        print(
            "Error: uvicorn is required for 'hawkapi dev'. "
            "Install it with: pip install hawkapi[uvicorn]",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Starting HawkAPI dev server: {args.app}")
    uvicorn.run(
        args.app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def _run_diff(args: argparse.Namespace) -> int:
    """Compare two HawkAPI apps and report breaking changes."""
    old_module_path, old_attr = _parse_ref(args.old)
    new_module_path, new_attr = _parse_ref(args.new)

    old_mod = importlib.import_module(old_module_path)
    new_mod = importlib.import_module(new_module_path)

    old_spec = _load_app_spec(old_mod, old_attr)
    new_spec = _load_app_spec(new_mod, new_attr)

    changes = _diff_specs(old_spec, new_spec)

    if not changes:
        print("No API changes detected.")
        return 0

    print(format_report(changes))
    has_breaking = any(c.severity.name == "BREAKING" for c in changes)
    return 1 if has_breaking else 0


def _load_app_spec(module: ModuleType, attr_name: str = "app") -> dict[str, Any]:
    """Load a HawkAPI app from a module and generate its OpenAPI spec."""
    app = getattr(module, attr_name)
    return generate_openapi(app.routes, title=app.title, version=app.version)


def _diff_specs(old_spec: dict[str, Any], new_spec: dict[str, Any]) -> list[Change]:
    """Compare two OpenAPI specs and return changes."""
    return detect_breaking_changes(old_spec, new_spec)


def _parse_ref(ref: str) -> tuple[str, str]:
    """Parse 'module.path:attr' into (module_path, attr_name)."""
    if ":" in ref:
        module_path, attr = ref.rsplit(":", 1)
        return module_path, attr
    return ref, "app"


if __name__ == "__main__":
    main()
