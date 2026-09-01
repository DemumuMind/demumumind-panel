"""App version — SSOT read from pyproject.toml.

pyproject.toml is the single editable source of truth. This module falls
back to installed metadata and then a literal default only if pyproject
is unavailable (e.g. running from a bare checkout without install).
"""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_VERSION = "0.2.0"


def _read_version() -> str:
    try:
        import tomllib

        pyproject = _PROJECT_ROOT / "pyproject.toml"
        if pyproject.exists():
            with pyproject.open("rb") as fh:
                data = tomllib.load(fh)
            return str(data.get("project", {}).get("version", _DEFAULT_VERSION))
    except Exception:
        pass
    try:
        from importlib.metadata import version

        return version("demumumind-panel")
    except Exception:
        return _DEFAULT_VERSION


VERSION = _read_version()
__version__ = VERSION

__all__ = ["VERSION", "__version__"]
