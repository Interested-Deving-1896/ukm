"""
XanMod kernel provider.

XanMod publishes x86-64 .deb packages via a signed apt repository.
Flavors: edge, lts, rt (real-time), and ISA-level variants v1–v4.

Repository: https://xanmod.org
"""

from __future__ import annotations

import re
from typing import Iterator

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion
from ukm.core.providers.base import KernelProvider
from ukm.core.system import system_info

_XANMOD_REPO_LINE = (
    "deb [signed-by=/usr/share/keyrings/xanmod-archive-keyring.gpg] "
    "http://deb.xanmod.org releases main"
)
_XANMOD_KEY_URL = "https://dl.xanmod.org/archive.key"

# XanMod only publishes amd64 packages
_SUPPORTED_ARCHES = ["amd64"]

# Known XanMod package name prefixes
_XANMOD_PREFIXES = (
    "linux-xanmod",
    "linux-image-xanmod",
    "linux-headers-xanmod",
)

# ISA-level flavors and their CPU requirements
XANMOD_FLAVORS = {
    "v1":   "Any x86-64 CPU (safe default)",
    "v2":   "SSE4.2+ (~2008 onwards)",
    "v3":   "AVX2+ (Intel Haswell / AMD Ryzen+)",
    "v4":   "AVX-512 (high-end modern CPUs)",
    "edge": "Latest upstream, may be less stable",
    "lts":  "Long-term support release",
    "rt":   "PREEMPT_RT real-time kernel",
}


class XanModProvider(KernelProvider):

    @property
    def id(self) -> str:
        return "xanmod"

    def recommended_flavor(self) -> str:
        """Return the highest XanMod ISA level the current CPU supports."""
        from ukm.core.cpu import recommended_xanmod_level
        return recommended_xanmod_level()

    @property
    def display_name(self) -> str:
        return "XanMod"

    @property
    def family(self) -> KernelFamily:
        return KernelFamily.XANMOD

    @property
    def supported_arches(self) -> list[str]:
        return _SUPPORTED_ARCHES

    def is_available(self) -> bool:
        import shutil
        return bool(shutil.which("apt-get")) and system_info().arch == "amd64"

    def availability_reason(self) -> str:
        return (
            "XanMod kernels are only available for x86-64 (amd64) systems "
            "running a Debian/Ubuntu-based distribution."
        )

    def is_repo_configured(self) -> bool:
        """Return True if the XanMod apt repository is already set up."""
        import subprocess
        rc, out, _ = self._backend._run(["apt-cache", "search", "linux-xanmod"])
        return rc == 0 and "xanmod" in out.lower()

    def setup_repo(self) -> Iterator[str]:
        """Add the XanMod repository and import its signing key."""
        from ukm.core.backends.apt import AptBackend
        if not isinstance(self._backend, AptBackend):
            raise RuntimeError("XanMod repo setup requires an apt backend.")
        yield "Adding XanMod repository...\n"
        rc, out, err = self._backend.add_repository(_XANMOD_REPO_LINE, _XANMOD_KEY_URL)
        if out:
            yield out
        if err:
            yield err
        if rc != 0:
            raise RuntimeError(f"Failed to add XanMod repository (exit {rc})")
        rc2, out2, err2 = self._backend.refresh_cache()
        if out2:
            yield out2
        if err2:
            yield err2
        yield "XanMod repository configured.\n"

    # ------------------------------------------------------------------

    def list(self, arch: str, refresh: bool = False) -> list[KernelEntry]:
        if arch not in _SUPPORTED_ARCHES:
            return []

        if refresh:
            self._backend.refresh_cache()

        # Query apt cache for all xanmod packages
        rc, out, _ = self._backend._run(
            ["apt-cache", "search", "--names-only", "linux-xanmod"]
        )
        if rc != 0:
            return []

        installed_raw = self._backend.installed_packages("linux-xanmod")
        running = system_info().running_kernel
        entries: dict[str, KernelEntry] = {}

        for line in out.splitlines():
            pkg_name = line.split()[0] if line.split() else ""
            if not pkg_name.startswith("linux-xanmod"):
                continue

            # Extract version and flavor from package name
            # e.g. linux-xanmod-edge, linux-xanmod-lts, linux-xanmod-rt-v4
            flavor = self._flavor_from_pkg(pkg_name)
            ver_str = self._version_from_apt(pkg_name)
            if not ver_str:
                continue

            key = f"{ver_str}-{flavor}"
            if key in entries:
                continue

            is_inst = pkg_name in installed_raw
            is_run = running and ver_str in running

            status = KernelStatus.AVAILABLE
            if is_run:
                status = KernelStatus.RUNNING
            elif is_inst:
                status = KernelStatus.INSTALLED
            if self._backend.is_held(pkg_name):
                status = KernelStatus.HELD

            entries[key] = KernelEntry(
                version=KernelVersion(ver_str),
                family=self.family,
                provider_id=self.id,
                arch=arch,
                flavor=flavor,
                description=XANMOD_FLAVORS.get(flavor, ""),
                status=status,
                held=self._backend.is_held(pkg_name),
            )

        recommended = self.recommended_flavor()
        result = sorted(entries.values(), key=lambda e: (e.version, e.flavor), reverse=True)
        for entry in result:
            if entry.flavor == recommended and not entry.description:
                entry.description = (
                    f"{XANMOD_FLAVORS.get(recommended, '')} ★ recommended for this CPU"
                )
            elif entry.flavor == recommended:
                entry.description += " ★ recommended for this CPU"
        return result

    def install(self, entry: KernelEntry) -> Iterator[str]:
        from ukm.core.system import privilege_escalation_cmd
        pkg = self._pkg_name(entry)
        headers_pkg = pkg.replace("linux-xanmod", "linux-headers-xanmod")
        yield f"Installing {pkg} and {headers_pkg}...\n"
        cmd = privilege_escalation_cmd() + [
            "apt-get", "install", "-y", "--no-install-recommends", pkg, headers_pkg
        ]
        rc = 0
        for line in self._backend.stream(cmd):
            yield line
            if "E:" in line or "error" in line.lower():
                rc = 1
        if rc != 0:
            raise RuntimeError(f"Installation failed for {pkg}")
        yield f"XanMod kernel {entry.display_name} installed.\n"

    def remove(self, entry: KernelEntry, purge: bool = False) -> Iterator[str]:
        pkg = self._pkg_name(entry)
        yield f"Removing {pkg}...\n"
        pkgs = [p for p in self._backend.installed_packages("linux-xanmod") if str(entry.version) in p]
        if not pkgs:
            yield "No matching packages found.\n"
            return
        rc, out, err = self._backend.remove(pkgs, purge=purge)
        if out:
            yield out
        if err:
            yield err
        if rc != 0:
            raise RuntimeError(f"Removal failed (exit {rc})")
        yield f"XanMod kernel {entry.display_name} removed.\n"

    def hold(self, entry: KernelEntry) -> tuple[int, str, str]:
        pkgs = [p for p in self._backend.installed_packages("linux-xanmod") if str(entry.version) in p]
        return self._backend.hold(pkgs) if pkgs else (0, "Nothing to hold.", "")

    def unhold(self, entry: KernelEntry) -> tuple[int, str, str]:
        pkgs = [p for p in self._backend.installed_packages("linux-xanmod") if str(entry.version) in p]
        return self._backend.unhold(pkgs) if pkgs else (0, "Nothing to unhold.", "")

    # ------------------------------------------------------------------

    @staticmethod
    def _flavor_from_pkg(pkg: str) -> str:
        """Extract flavor from package name like linux-xanmod-edge or linux-xanmod-rt-v4."""
        suffix = pkg.replace("linux-xanmod", "").lstrip("-")
        for flavor in ("edge", "lts", "rt-v4", "rt-v3", "rt-v2", "rt-v1", "rt", "v4", "v3", "v2", "v1"):
            if suffix.startswith(flavor):
                return flavor
        return "stable"

    def _version_from_apt(self, pkg: str) -> str:
        """Query apt-cache show for the package version."""
        rc, out, _ = self._backend._run(["apt-cache", "show", pkg])
        if rc != 0:
            return ""
        for line in out.splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
        return ""

    @staticmethod
    def _pkg_name(entry: KernelEntry) -> str:
        flavor = entry.flavor
        if flavor and flavor not in ("stable", "generic"):
            return f"linux-xanmod-{flavor}"
        return "linux-xanmod"
