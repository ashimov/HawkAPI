"""HawkAPI CLI — development server launcher."""

from __future__ import annotations

import argparse
import sys


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

    # `hawkapi new` subcommand
    new_parser = subparsers.add_parser("new", help="Create a new HawkAPI project")
    new_parser.add_argument("name", help="Project name")
    new_parser.add_argument(
        "--docker", action="store_true", help="Include Dockerfile"
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "dev":
        _run_dev(args)
    elif args.command == "new":
        _run_new(args)


def _run_new(args: argparse.Namespace) -> None:
    """Scaffold a new HawkAPI project."""
    import os

    from hawkapi._scaffold.templates import generate_project

    project_dir = os.path.join(os.getcwd(), args.name)
    if os.path.exists(project_dir):
        print(f"Error: directory '{args.name}' already exists", file=sys.stderr)
        sys.exit(1)
    generate_project(project_dir, name=args.name, docker=args.docker)
    print(f"Created project '{args.name}' in ./{args.name}/")
    print(f"  cd {args.name} && uv sync && hawkapi dev main:app")


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


if __name__ == "__main__":
    main()
