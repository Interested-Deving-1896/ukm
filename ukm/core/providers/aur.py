"""
AUR (Arch User Repository) kernel provider.

Installs AUR kernel packages via yay, paru, or makepkg (in that preference
order). Covers kernels not in the official Arch repos:
  linux-cachyos, linux-tkg-*, linux-xanmod (AUR variant),
  linux-lqx (Liquorix for Arch), linux-rt-lts, linux-hardened-git, etc.

AUR operations always run as the current user (never root). The AUR helper
handles privilege escalation internally for the final pacman -U step.
"""

from __future__ import annotations

import shutil
import subprocess  # used in _makepkg_cmd
from collections.abc import Iterator

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion
from ukm.core.providers.base import KernelProvider
from ukm.core.system import system_info

# Well-known AUR kernel packages
_AUR_KERNELS = [
    "linux-cachyos",
    "linux-cachyos-lts",
    "linux-cachyos-bore",
    "linux-cachyos-bore-lts",
    "linux-tkg-pds",
    "linux-tkg-bmq",
    "linux-tkg-cfs",
    "linux-lqx",  # Liquorix for Arch
    "linux-xanmod",  # XanMod AUR variant
    "linux-xanmod-lts",
    "linux-hardened-git",
    "linux-rt",
    "linux-rt-lts",
    "linux-clear",  # Intel Clear Linux patches
    "linux-nitrous",  # Nitrous kernel
    "linux-zen-git",
]

_AUR_DESCRIPTIONS = {
    "linux-cachyos": "CachyOS optimised kernel (BORE scheduler)",
    "linux-cachyos-lts": "CachyOS LTS kernel",
    "linux-cachyos-bore": "CachyOS BORE scheduler kernel",
    "linux-cachyos-bore-lts": "CachyOS BORE LTS kernel",
    "linux-tkg-pds": "TkG kernel with PDS scheduler",
    "linux-tkg-bmq": "TkG kernel with BMQ scheduler",
    "linux-tkg-cfs": "TkG kernel with CFS (stock scheduler)",
    "linux-lqx": "Liquorix low-latency kernel for Arch",
    "linux-xanmod": "XanMod performance kernel (AUR)",
    "linux-xanmod-lts": "XanMod LTS kernel (AUR)",
    "linux-hardened-git": "Hardened kernel (git)",
    "linux-rt": "PREEMPT_RT real-time kernel",
    "linux-rt-lts": "PREEMPT_RT LTS real-time kernel",
    "linux-clear": "Intel Clear Linux patches kernel",
    "linux-nitrous": "Nitrous kernel (optimised for modern CPUs)",
    "linux-zen-git": "Zen kernel (git)",
}


def _aur_helper() -> str | None:
    """Return the first available AUR helper, or None."""
    for helper in ("yay", "paru"):
        if shutil.which(helper):
            return helper
    return None


class AURProvider(KernelProvider):
    @property
    def id(self) -> str:
        return "aur"

    @property
    def display_name(self) -> str:
        return "AUR"

    @property
    def family(self) -> KernelFamily:
        return KernelFamily.DISTRO

    @property
    def supported_arches(self) -> list[str]:
        # AUR is Arch-only; Arch supports amd64 (x86_64) and arm64 (aarch64)
        return ["amd64", "arm64", "armhf"]

    def is_available(self) -> bool:
        return bool(shutil.which("pacman")) and (
            bool(_aur_helper()) or bool(shutil.which("makepkg"))
        )

    def availability_reason(self) -> str:
        if not shutil.which("pacman"):
            return "AUR provider requires pacman (Arch Linux)."
        return (
            "No AUR helper found. Install yay or paru, or ensure makepkg is available.\n"
            "  yay:  https://github.com/Jguer/yay\n"
            "  paru: https://github.com/morganamilo/paru"
        )

    def helper(self) -> str | None:
        return _aur_helper()

    # ------------------------------------------------------------------
    # list()
    # ------------------------------------------------------------------

    def fetch(self, arch: str, refresh: bool = False) -> list[KernelEntry]:
        if arch not in self.supported_arches:
            return []

        running = system_info().running_kernel
        result: list[KernelEntry] = []

        for pkg in _AUR_KERNELS:
            ver_str, is_inst = self._query_pkg(pkg)
            if not ver_str:
                continue

            is_run = running and (pkg in running or ver_str.split("-")[0] in running)
            status = (
                KernelStatus.RUNNING
                if is_run
                else (KernelStatus.INSTALLED if is_inst else KernelStatus.AVAILABLE)
            )
            if self._backend.is_held(pkg):
                status = KernelStatus.HELD

            result.append(
                KernelEntry(
                    version=KernelVersion(ver_str),
                    family=self.family,
                    provider_id=self.id,
                    arch=arch,
                    flavor=pkg,
                    description=_AUR_DESCRIPTIONS.get(pkg, f"AUR: {pkg}"),
                    status=status,
                    held=self._backend.is_held(pkg),
                    source_url=f"https://aur.archlinux.org/packages/{pkg}",
                )
            )

        return sorted(result, key=lambda e: e.version, reverse=True)

    # ------------------------------------------------------------------
    # install()
    # ------------------------------------------------------------------

    def install(self, entry: KernelEntry) -> Iterator[str]:
        pkg = entry.flavor
        helper = _aur_helper()

        if helper:
            yield f"Installing {pkg} via {helper}...\n"
            cmd: list[str] = [helper, "-S", "--noconfirm", pkg]
        else:
            yield f"Installing {pkg} via makepkg (no AUR helper found)...\n"
            makepkg_cmd = self._makepkg_cmd(pkg)
            if makepkg_cmd is None:
                raise RuntimeError(f"Cannot install {pkg}: no AUR helper and makepkg clone failed.")
            cmd = makepkg_cmd

        rc = 0
        for line in self._backend.stream(cmd):
            yield line
            if "error:" in line.lower():
                rc = 1

        if rc != 0:
            raise RuntimeError(f"AUR install failed for {pkg}")
        yield f"{pkg} installed.\n"

    # ------------------------------------------------------------------
    # remove()
    # ------------------------------------------------------------------

    def remove(self, entry: KernelEntry, purge: bool = False) -> Iterator[str]:
        pkg = entry.flavor
        yield f"Removing {pkg}...\n"
        rc, out, err = self._backend.remove([pkg], purge=purge)
        if out:
            yield out
        if err:
            yield err
        if rc != 0:
            raise RuntimeError(f"Removal failed for {pkg} (exit {rc})")
        yield f"{pkg} removed.\n"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query_pkg(self, pkg: str) -> tuple[str, bool]:
        """
        Return (version_str, is_installed) for a package.
        Queries the AUR helper or pacman -Si / pacman -Q.
        """
        # Check if installed locally first
        rc_q, out_q, _ = self._backend._run(["pacman", "-Q", pkg])
        is_inst = rc_q == 0
        if is_inst:
            # e.g. "linux-cachyos 6.9.0.cachyos1-1"
            parts = out_q.strip().split()
            ver = parts[1] if len(parts) >= 2 else ""
            return ver, True

        # Query AUR for available version
        helper = _aur_helper()
        if helper:
            rc, out, _ = self._backend._run([helper, "-Si", pkg])
            if rc == 0:
                for line in out.splitlines():
                    if line.strip().startswith("Version"):
                        ver = line.split(":", 1)[1].strip()
                        return ver, False
        else:
            # Fall back to AUR RPC
            ver = AURProvider._aur_rpc_version(pkg)
            if ver:
                return ver, False

        return "", False

    @staticmethod
    def _aur_rpc_version(pkg: str) -> str:
        """Query the AUR RPC API for the latest version of a package."""
        import json
        import urllib.request

        url = f"https://aur.archlinux.org/rpc/v5/info?arg[]={pkg}"
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                data = json.loads(r.read())
            results = data.get("results", [])
            if results:
                return results[0].get("Version", "")
        except Exception:
            pass
        return ""

    def _makepkg_cmd(self, pkg: str) -> list[str] | None:
        """
        Clone the AUR package and return the makepkg install command.
        Returns None if the clone fails.
        """
        import tempfile

        tmpdir = tempfile.mkdtemp(prefix="ukm-aur-")
        clone_url = f"https://aur.archlinux.org/{pkg}.git"
        rc = subprocess.run(
            ["git", "clone", "--depth=1", clone_url, tmpdir],
            capture_output=True,
        ).returncode
        if rc != 0:
            return None
        return ["makepkg", "-si", "--noconfirm", "--dir", tmpdir]
