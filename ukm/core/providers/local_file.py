"""
Local file provider.

Installs a kernel from a locally supplied package file:
  .deb        → dpkg (apt backend)
  .rpm        → rpm/dnf (dnf/zypper backend)
  .pkg.tar.*  → pacman (pacman backend)
  .apk        → apk (apk backend)

The provider detects the file type and delegates to the appropriate backend.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion
from ukm.core.providers.base import KernelProvider


class LocalFileProvider(KernelProvider):

    @property
    def id(self) -> str:
        return "local_file"

    @property
    def display_name(self) -> str:
        return "Local File"

    @property
    def family(self) -> KernelFamily:
        return KernelFamily.LOCAL

    @property
    def supported_arches(self) -> list[str]:
        return ["*"]

    def is_available(self) -> bool:
        return self._backend.is_available()

    # ------------------------------------------------------------------

    def list(self, arch: str, refresh: bool = False) -> list[KernelEntry]:
        # Local file provider has no persistent list; entries are created
        # on demand when the user selects a file via the GUI or CLI.
        return []

    def entry_from_path(self, path: str, arch: str) -> KernelEntry:
        """Create a KernelEntry from a local package file path."""
        p = Path(path)
        ver_str = self._version_from_filename(p.name) or "unknown"
        return KernelEntry(
            version=KernelVersion(ver_str),
            family=self.family,
            provider_id=self.id,
            arch=arch,
            flavor=self._flavor_from_filename(p.name),
            description=str(p),
            status=KernelStatus.AVAILABLE,
            source_url=str(p),
        )

    def install(self, entry: KernelEntry) -> Iterator[str]:
        path = entry.source_url or entry.description
        if not path or not Path(path).exists():
            raise RuntimeError(f"File not found: {path}")

        yield f"Installing from {path}...\n"
        rc, out, err = self._backend.install_local([path])
        if out:
            yield out
        if err:
            yield err
        if rc != 0:
            raise RuntimeError(f"Installation failed (exit {rc})")
        yield "Local kernel installed.\n"

    def remove(self, entry: KernelEntry, purge: bool = False) -> Iterator[str]:
        # Removal works the same as any other installed kernel
        ver = str(entry.version)
        yield f"Removing kernel {ver}...\n"
        pkgs = [p for p in self._backend.installed_packages("linux-") if ver in p]
        if not pkgs:
            yield "No matching installed packages found.\n"
            return
        rc, out, err = self._backend.remove(pkgs, purge=purge)
        if out:
            yield out
        if err:
            yield err
        if rc != 0:
            raise RuntimeError(f"Removal failed (exit {rc})")
        yield f"Kernel {ver} removed.\n"

    # ------------------------------------------------------------------

    @staticmethod
    def _version_from_filename(name: str) -> str:
        m = re.search(r"(\d+\.\d+[\d.]*[^\s_]*)", name)
        return m.group(1) if m else ""

    @staticmethod
    def _flavor_from_filename(name: str) -> str:
        for flavor in ("generic", "lowlatency", "rt", "zen", "hardened", "lts"):
            if flavor in name.lower():
                return flavor
        return "custom"
