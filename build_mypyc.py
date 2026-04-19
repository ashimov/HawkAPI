"""mypyc compilation entry point for HawkAPI hot-path modules.

Compilation is OPT-IN. Set the environment variable ``HAWKAPI_BUILD_MYPYC=1``
when building (e.g. ``HAWKAPI_BUILD_MYPYC=1 uv build --wheel`` or
``HAWKAPI_BUILD_MYPYC=1 pip install hawkapi --no-binary hawkapi``).

When the env var is unset, this module returns an empty extension list and the
package installs as pure Python — preserving the default ``pip install hawkapi``
behaviour and PyPy compatibility.

The selected modules are pure-typed hot paths: route lookup (radix tree, route
record, param converters), response writers (Response, JSONResponse) and the
ASGI middleware pipeline builder. Each remains importable as plain Python when
the compiled ``.so`` is absent — there are no compile-only constructs.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

# Modules selected for mypyc compilation. Paths are relative to the project root
# (the directory containing ``pyproject.toml``).
#
# IMPORTANT: ``responses/response.py`` and ``responses/json_response.py`` are
# intentionally EXCLUDED because user code (and the bundled
# ``PlainTextResponse``/``HTMLResponse``/``RedirectResponse`` helpers) subclasses
# them. mypyc rejects ``interpreted classes cannot inherit from compiled``
# subclassing at runtime, so compiling these would break the public API.
# Compiling the radix tree, route record, param converters and middleware
# pipeline still captures the dominant request-routing hot path.
HOT_MODULES: tuple[str, ...] = (
    "src/hawkapi/routing/_radix_tree.py",
    "src/hawkapi/routing/route.py",
    "src/hawkapi/routing/param_converters.py",
    "src/hawkapi/middleware/_pipeline.py",
    # Added in Wave 3: router registration path (hot at startup, also called
    # on include_router) and the plan-based dependency resolver (hot per
    # request on every non-trivial route). Both are pure-typed with no
    # subclassing constraints from user code, so mypyc can compile them freely.
    "src/hawkapi/routing/router.py",
    "src/hawkapi/di/resolver.py",
    # NOTE: app.py is intentionally EXCLUDED — HawkAPI(Router) is subclassed
    # by user code and mypyc does not allow interpreted classes to inherit from
    # compiled ones at runtime.
    # NOTE: requests/request.py is intentionally EXCLUDED — Request is also
    # subclassed by user code via TestClient and custom request overrides.
)


def is_enabled() -> bool:
    """Return True when mypyc compilation has been opted into.

    mypyc-compiled extensions require the GIL. On a PEP 703 free-threaded
    CPython build (``python3.13t``), ``sys._is_gil_enabled()`` returns
    ``False`` — we skip compilation in that case even when the env var is set,
    and warn on stderr so the build log explains the decision.
    """
    if os.environ.get("HAWKAPI_BUILD_MYPYC", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False

    is_gil_enabled = getattr(sys, "_is_gil_enabled", None)
    if is_gil_enabled is not None and not is_gil_enabled():
        print(
            "HAWKAPI_BUILD_MYPYC is set but the interpreter is free-threaded; "
            "skipping mypyc compilation.",
            file=sys.stderr,
        )
        return False

    return True


def build_extensions() -> Sequence[Any]:
    """Return the list of mypyc-built ``Extension`` objects.

    Returns an empty list when ``HAWKAPI_BUILD_MYPYC`` is not set so the build
    backend can skip the C compilation step entirely.
    """
    if not is_enabled():
        return []

    # Import lazily so pure-Python builds never need ``mypy`` installed.
    from mypyc.build import mypycify  # noqa: PLC0415

    return mypycify(
        list(HOT_MODULES),
        strip_asserts=False,
        # Give the shared mypyc helper module a stable, namespaced name so it
        # cannot collide with other mypyc-compiled packages on the same
        # interpreter (otherwise mypyc generates a random hash-based name).
        group_name="hawkapi_hot",
    )
