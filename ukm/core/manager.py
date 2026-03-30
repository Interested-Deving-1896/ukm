"""
KernelManager — the central coordinator.

Aggregates all providers, manages per-kernel notes and locks (persisted to
~/.config/ukm/state.json), and exposes a single unified API used by both
the CLI and the GUI.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from pathlib import Path

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus
from ukm.core.providers import get_providers
from ukm.core.providers.base import KernelProvider
from ukm.core.system import system_info

_STATE_FILE = Path.home() / ".config" / "ukm" / "state.json"


class KernelManager:

    def __init__(self, arch: str | None = None) -> None:
        self._arch = arch or system_info().arch
        self._providers: list[KernelProvider] = get_providers(self._arch)
        self._state: dict = self._load_state()

    # ------------------------------------------------------------------
    # Provider access
    # ------------------------------------------------------------------

    @property
    def providers(self) -> list[KernelProvider]:
        return self._providers

    def provider(self, provider_id: str) -> KernelProvider | None:
        return next((p for p in self._providers if p.id == provider_id), None)

    # ------------------------------------------------------------------
    # Kernel listing
    # ------------------------------------------------------------------

    def list_all(self, refresh: bool = False) -> list[KernelEntry]:
        """Return all kernels from all available providers, sorted newest first."""
        entries: list[KernelEntry] = []
        for provider in self._providers:
            with contextlib.suppress(Exception):
                entries.extend(provider.list(self._arch, refresh=refresh))
        # Apply persisted notes and locks
        for entry in entries:
            key = self._state_key(entry)
            entry.notes = self._state.get("notes", {}).get(key, "")
            if self._state.get("locked", {}).get(key):
                entry.held = True
                if entry.status == KernelStatus.INSTALLED:
                    entry.status = KernelStatus.HELD
        return sorted(entries, key=lambda e: e.version, reverse=True)

    def list_by_family(self, family: KernelFamily, refresh: bool = False) -> list[KernelEntry]:
        return [e for e in self.list_all(refresh=refresh) if e.family == family]

    def list_installed(self) -> list[KernelEntry]:
        return [e for e in self.list_all() if e.is_installed]

    def running_kernel(self) -> KernelEntry | None:
        for e in self.list_all():
            if e.is_running:
                return e
        return None

    # ------------------------------------------------------------------
    # Install / Remove
    # ------------------------------------------------------------------

    def install(self, entry: KernelEntry) -> Iterator[str]:
        provider = self.provider(entry.provider_id)
        if provider is None:
            raise RuntimeError(f"Provider '{entry.provider_id}' not found.")
        if not provider.is_available():
            raise RuntimeError(
                f"Provider '{provider.display_name}' is not available: "
                f"{provider.availability_reason()}"
            )
        yield from provider.install(entry)
        # Rebuild DKMS modules for the newly installed kernel
        from ukm.core import dkms
        yield from dkms.autoinstall(str(entry.version))

    def remove(self, entry: KernelEntry, purge: bool = False) -> Iterator[str]:
        if entry.is_running:
            raise RuntimeError("Cannot remove the currently running kernel.")
        if entry.held:
            raise RuntimeError(
                f"Kernel {entry.display_name} is locked. Unlock it first."
            )
        provider = self.provider(entry.provider_id)
        if provider is None:
            raise RuntimeError(f"Provider '{entry.provider_id}' not found.")
        yield from provider.remove(entry, purge=purge)
        # Clean up DKMS module builds for the removed kernel
        from ukm.core import dkms
        yield from dkms.remove_kernel(str(entry.version))

    # ------------------------------------------------------------------
    # Hold / Lock
    # ------------------------------------------------------------------

    def hold(self, entry: KernelEntry) -> tuple[int, str, str]:
        provider = self.provider(entry.provider_id)
        if provider is None:
            return 1, "", f"Provider '{entry.provider_id}' not found."
        rc, out, err = provider.hold(entry)
        if rc == 0:
            self._set_locked(entry, True)
        return rc, out, err

    def unhold(self, entry: KernelEntry) -> tuple[int, str, str]:
        provider = self.provider(entry.provider_id)
        if provider is None:
            return 1, "", f"Provider '{entry.provider_id}' not found."
        rc, out, err = provider.unhold(entry)
        if rc == 0:
            self._set_locked(entry, False)
        return rc, out, err

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def set_note(self, entry: KernelEntry, note: str) -> None:
        key = self._state_key(entry)
        self._state.setdefault("notes", {})[key] = note
        entry.notes = note
        self._save_state()

    def get_note(self, entry: KernelEntry) -> str:
        return self._state.get("notes", {}).get(self._state_key(entry), "")

    # ------------------------------------------------------------------
    # Remove old kernels
    # ------------------------------------------------------------------

    def remove_old(self, keep: int = 1, purge: bool = False) -> Iterator[str]:
        """
        Remove all installed kernels except the running one and the
        `keep` most recent ones. Locked kernels are always preserved.
        """
        installed = sorted(
            [e for e in self.list_installed() if not e.is_running and not e.held],
            key=lambda e: e.version,
            reverse=True,
        )
        to_remove = installed[keep:]
        if not to_remove:
            yield "No old kernels to remove.\n"
            return
        for entry in to_remove:
            yield f"Removing {entry.display_name}...\n"
            yield from self.remove(entry, purge=purge)

    # ------------------------------------------------------------------
    # Secure boot warning
    # ------------------------------------------------------------------

    def secure_boot_warning(self) -> str | None:
        """Return a warning string if Secure Boot is enabled, else None."""
        if system_info().has_secure_boot:
            return (
                "Secure Boot is enabled on this system. "
                "Mainline, XanMod, and Liquorix kernels are unsigned and "
                "will not boot with Secure Boot enabled. "
                "Disable Secure Boot in your firmware settings, or use only "
                "your distribution's signed kernels."
            )
        return None

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _state_key(self, entry: KernelEntry) -> str:
        return f"{entry.provider_id}:{entry.version}:{entry.flavor}:{entry.arch}"

    def _set_locked(self, entry: KernelEntry, locked: bool) -> None:
        key = self._state_key(entry)
        self._state.setdefault("locked", {})[key] = locked
        self._save_state()

    def _load_state(self) -> dict:
        if _STATE_FILE.exists():
            try:
                return json.loads(_STATE_FILE.read_text())
            except Exception:
                pass
        return {"notes": {}, "locked": {}}

    def _save_state(self) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(self._state, indent=2))
