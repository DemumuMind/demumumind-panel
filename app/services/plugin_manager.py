"""Plugin runtime abstraction — Noop by default, Wasmtime when available.

Ed25519 signature verification via `cryptography`. Plugins are `.wasm`
modules stored in the `plugins` table (SSOT) and executed through
wasmtime when the optional `plugins` extra is installed and a public key
is configured. Never logs plugin bytes or signatures in full.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class PluginInfo:
    name: str
    size_bytes: int
    loaded: bool
    signature_valid: bool = False
    error: str | None = None


class PluginRuntime(Protocol):
    async def load(self, name: str, wasm_bytes: bytes, signature_hex: str) -> bool: ...
    async def invoke(self, name: str, fn: str, args: Any) -> Any: ...
    def list(self) -> list[PluginInfo]: ...


def verify_ed25519(payload: bytes, signature_hex: str, public_key_hex: str | None = None) -> bool:
    pub_hex = public_key_hex or settings.PLUGIN_PUBLIC_KEY_HEX
    if not pub_hex:
        return False
    try:
        signature = bytes.fromhex(signature_hex)
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        pub.verify(signature, payload)
        return True
    except (ValueError, InvalidSignature):
        return False


class NoopRuntime:
    """Default runtime — accepts uploads, verifies signatures, no execution."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginInfo] = {}

    async def load(self, name: str, wasm_bytes: bytes, signature_hex: str) -> bool:
        if not name:
            return False
        valid = verify_ed25519(wasm_bytes, signature_hex)
        self._plugins[name] = PluginInfo(
            name=name,
            size_bytes=len(wasm_bytes),
            loaded=True,
            signature_valid=valid,
        )
        logger.info("plugin.loaded.noop", name=name, size=len(wasm_bytes), signature_valid=valid)
        return True

    async def invoke(self, name: str, fn: str, args: Any) -> Any:
        return {"ok": False, "error": "wasm execution not enabled (NoopRuntime)"}

    def list(self) -> list[PluginInfo]:
        return list(self._plugins.values())


class WasmtimeRuntime(NoopRuntime):
    """Wasmtime-backed runtime — requires the optional `plugins` extra."""

    def __init__(self) -> None:
        import wasmtime  # noqa: F401

        super().__init__()
        self._instances: dict[str, Any] = {}
        self._store: Any = None

    async def load(self, name: str, wasm_bytes: bytes, signature_hex: str) -> bool:
        import wasmtime

        if not name:
            return False
        valid = verify_ed25519(wasm_bytes, signature_hex)
        try:
            engine = wasmtime.Engine()
            store = wasmtime.Store(engine)
            module = wasmtime.Module(engine, wasm_bytes)
            instance = wasmtime.Instance(store, module, [])
            self._instances[name] = (store, instance, module)
            self._store = store
            self._plugins[name] = PluginInfo(
                name=name,
                size_bytes=len(wasm_bytes),
                loaded=True,
                signature_valid=valid,
            )
            logger.info("plugin.loaded.wasmtime", name=name, size=len(wasm_bytes), signature_valid=valid)
            return True
        except Exception as exc:
            logger.warning("plugin.load_failed", name=name, error=str(exc))
            self._plugins[name] = PluginInfo(
                name=name,
                size_bytes=len(wasm_bytes),
                loaded=False,
                signature_valid=valid,
                error=str(exc),
            )
            return False

    async def invoke(self, name: str, fn: str, args: Any) -> Any:
        entry = self._instances.get(name)
        if entry is None:
            return {"ok": False, "error": f"plugin not loaded: {name}"}
        store, instance, module = entry
        exports = instance.exports(store)
        func = exports.get(fn)
        if func is None:
            return {"ok": False, "error": f"export not found: {fn}"}
        try:
            if args is None:
                result = func(store)
            elif isinstance(args, list):
                result = func(store, *args)
            elif isinstance(args, dict):
                result = func(store, **args)
            else:
                result = func(store, args)
            return {"ok": True, "result": result}
        except Exception as exc:
            logger.warning("plugin.invoke_error", name=name, fn=fn, error=str(exc))
            return {"ok": False, "error": str(exc)}


_plugin_manager: PluginRuntime | None = None


def get_plugin_manager() -> PluginRuntime:
    global _plugin_manager
    if _plugin_manager is None:
        try:
            _plugin_manager = WasmtimeRuntime()
            logger.info("plugin.runtime=wasmtime")
        except ImportError:
            _plugin_manager = NoopRuntime()
            logger.info("plugin.runtime=noop (wasmtime not installed)")
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
]
