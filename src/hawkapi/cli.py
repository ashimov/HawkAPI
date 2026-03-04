"""HawkAPI CLI — development server launcher and API tools."""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import Any


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

    # `hawkapi changelog` subcommand
    changelog_parser = subparsers.add_parser(
        "changelog",
        help="Generate Markdown changelog between two app versions",
    )
    changelog_parser.add_argument(
        "old_app",
        help="Old application ref (module:attribute format, e.g. old_app:app)",
    )
    changelog_parser.add_argument(
        "new_app",
        help="New application ref (module:attribute format, e.g. new_app:app)",
    )
    changelog_parser.add_argument(
        "--title",
        default="API Changelog",
        help="Title for the changelog (default: 'API Changelog')",
    )
    changelog_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output file path (default: print to stdout)",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "dev":
        _run_dev(args)
    elif args.command == "changelog":
        _run_changelog(args)


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


def _parse_ref(ref: str) -> tuple[str, str]:
    """Parse a ``module:attribute`` reference into its components.

    Raises :class:`SystemExit` with a helpful message when the format is
    invalid.
    """
    if ":" not in ref:
        print(
            f"Error: invalid app reference '{ref}'. "
            "Expected 'module:attribute' format (e.g. myapp:app).",
            file=sys.stderr,
        )
        sys.exit(1)
    module_path, _, attribute = ref.partition(":")
    return module_path, attribute


def _load_app_spec(ref: str) -> dict[str, Any]:
    """Import a HawkAPI application from *ref* and return its OpenAPI spec.

    *ref* must be in ``module:attribute`` format (e.g. ``myapp:app``).
    """
    module_path, attribute = _parse_ref(ref)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        print(f"Error: could not import module '{module_path}': {exc}", file=sys.stderr)
        sys.exit(1)

    app = getattr(module, attribute, None)
    if app is None:
        print(
            f"Error: module '{module_path}' has no attribute '{attribute}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not hasattr(app, "openapi"):
        print(
            f"Error: '{ref}' is not a HawkAPI application (missing .openapi() method).",
            file=sys.stderr,
        )
        sys.exit(1)

    return app.openapi()


def _diff_specs(old_spec: dict[str, Any], new_spec: dict[str, Any]) -> list[Any]:
    """Run breaking-change detection between two OpenAPI specs."""
    from hawkapi.openapi.breaking_changes import detect_breaking_changes

    return detect_breaking_changes(old_spec, new_spec)


def _run_changelog(args: argparse.Namespace) -> None:
    """Generate a Markdown changelog between two application versions."""
    from hawkapi.openapi.changelog import generate_changelog

    old_spec = _load_app_spec(args.old_app)
    new_spec = _load_app_spec(args.new_app)
    changes = _diff_specs(old_spec, new_spec)
    changelog = generate_changelog(changes, title=args.title)

    if args.output:
        with open(args.output, "w") as fh:
            fh.write(changelog)
        print(f"Changelog written to {args.output}")
    else:
        print(changelog)


if __name__ == "__main__":
    main()
