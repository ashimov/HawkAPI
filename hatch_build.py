"""Hatchling custom build hook that wires mypyc compilation into the wheel.

Activation is gated by the ``HAWKAPI_BUILD_MYPYC`` environment variable (see
``build_mypyc.py``). When the variable is unset the hook is a no-op and the
wheel ships pure Python — preserving the default ``pip install hawkapi``
behaviour.

When the variable is set the hook:

1. Calls ``mypyc.build.mypycify`` on the configured hot modules.
2. Drives setuptools' ``build_ext`` in-place to produce ``.so`` files next to
   the source ``.py`` files.
3. Force-includes each generated ``.so`` into the wheel under its
   ``hawkapi/...`` package path. The ``.py`` source files are also kept so the
   pure-Python fallback works on any platform that cannot load the binary.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

if TYPE_CHECKING:
    from collections.abc import Iterator


class MypycBuildHook(BuildHookInterface[Any]):
    """Compile selected hot modules with mypyc when opted in."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        # Lazy import so the hook module itself stays import-safe even when
        # ``mypy``/``setuptools`` are absent (pure-Python build path).
        root = str(Path(self.root).resolve())
        sys.path.insert(0, root)
        try:
            import build_mypyc  # noqa: PLC0415
        finally:
            try:
                sys.path.remove(root)
            except ValueError:
                pass

        if not build_mypyc.is_enabled():
            return

        extensions = list(build_mypyc.build_extensions())
        if not extensions:
            return

        # Force a platform-tagged wheel since we are shipping compiled binaries.
        build_data["pure_python"] = False
        build_data["infer_tag"] = True

        compiled_paths = _run_build_ext(self.root, extensions)

        force_include = build_data.setdefault("force_include", {})
        for absolute_path, relative_target in compiled_paths:
            force_include[absolute_path] = relative_target


def _run_build_ext(
    project_root: str, extensions: list[Any]
) -> list[tuple[str, str]]:
    """Drive setuptools' ``build_ext --inplace`` and return compiled .so paths.

    Returns a list of ``(absolute_source_path, wheel_relative_target)`` pairs
    suitable for hatchling's ``force_include`` map.
    """
    from setuptools import Distribution  # noqa: PLC0415

    cwd = os.getcwd()
    os.chdir(project_root)
    try:
        dist = Distribution(
            {
                "name": "hawkapi",
                "ext_modules": extensions,
                "script_name": "hatch_build",
                "package_dir": {"": "src"},
            }
        )
        cmd = dist.get_command_obj("build_ext")
        cmd.inplace = 1  # type: ignore[attr-defined]
        cmd.ensure_finalized()
        cmd.run()
    finally:
        os.chdir(cwd)

    return list(_collect_compiled_artifacts(Path(project_root) / "src"))


def _collect_compiled_artifacts(src_root: Path) -> Iterator[tuple[str, str]]:
    """Yield ``(absolute_path, wheel_relative_path)`` for every .so under src."""
    for so_path in src_root.rglob("*.so"):
        relative = so_path.relative_to(src_root).as_posix()
        yield str(so_path), relative
