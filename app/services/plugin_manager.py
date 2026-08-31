"""Plugin runtime abstraction — Noop by default, Wasmtime optional.

Ed25519 signature verification via the `cryptography` library (not the
unmaintained `ed25519` package). Plugins are `.wasm` modules uploaded
with X-Plugin-Signature (hex) headers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = structlog.get_logger(__name__)

# In production, set this public key (hex, 64 chars) via environment config;
# the placeholder is only for local/dev signature checks.
PLUGIN_PUBLIC_KEY_HEX: str = ""


@dataclass
class PluginInfo:
    name: str
    size_bytes: int
    loaded: bool
    signature_valid: bool = False
    error: str | None = None


class PluginRuntime(Protocol):
    async def load(self, name: str, wasm_bytes: bytes, signature_hex: str) -> bool: ...
    async def invoke(self, name: str, fn: str, args: dict[str, Any]) -> Any: ...
    def list(self) -> list[PluginInfo]: ...


def verify_ed25519(payload: bytes, signature_hex: str, public_key_hex: str) -> bool:
    if not public_key_hex:
        return False
    try:
        signature = bytes.fromhex(signature_hex)
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        pub.verify(signature, payload)
        return True
    except (ValueError, InvalidSignature):
        return False


class NoopRuntime:
    """Default runtime — accepts uploads, records metadata, no execution."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginInfo] = {}

    async def load(self, name: str, wasm_bytes: bytes, signature_hex: str) -> bool:
        if not name:
            return False
        valid = verify_ed25519(wasm_bytes, signature_hex, PLUGIN_PUBLIC_KEY_HEX)
        self._plugins[name] = PluginInfo(
            name=name,
            size_bytes=len(wasm_bytes),
            loaded=True,
            signature_valid=valid,
        )
        logger.info("plugin.loaded.noop", name=name, size=len(wasm_bytes), signature_valid=valid)
        return True

    async def invoke(self, name: str, fn: str, args: dict[str, Any]) -> Any:
        return {"ok": False, "error": "noop runtime: wasm execution not enabled"}

    def list(self) -> list[PluginInfo]:
        return list(self._plugins.values())


class WasmtimeRuntime(NoopRuntime):
    """Wasmtime-backed runtime — requires the optional `plugins` extra."""

    def __init__(self) -> None:
        try:
            import wasmtime  # noqa: F401
        except ImportError:
            raise ImportError("wasmtime not installed — run: uv sync --extra plugins") from None
        super().__init__()
        self._engine: Any = None


_plugin_manager: PluginRuntime = NoopRuntime()


def get_plugin_manager() -> PluginRuntime:
    return _plugin_manager


def set_plugin_manager(runtime: PluginRuntime) -> None:
    global _plugin_manager
    _plugin_manager = runtime


__all__ = [
    "PluginInfo",
    "PluginRuntime",
    "NoopRuntime",
    "WasmtimeRuntime",
    "verify_ed25519",
    "get_plugin_manager",
    "set_plugin_manager",
    "PLUGIN_PUBLIC_KEY_HEX",
]
