"""
Distro-native kernel provider.

Queries the system's own package manager for kernel packages.
Works on all supported distros and all architectures — whatever the
distro ships is what this provider exposes.

Package name patterns per family:
  apt:     linux-image-*, linux-image-generic, linux-image-lts-*
  pacman:  linux, linux-lts, linux-zen, linux-hardened, linux-rt, linux-rt-lts
  dnf:     kernel, kernel-core, kernel-devel
  zypper:  kernel-default, kernel-default-devel, kernel-rt
  apk:     linux-lts, linux-edge, linux-virt, linux-rpi
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion
from ukm.core.providers.base import KernelProvider
from ukm.core.system import PackageManagerKind, system_info

# Per-backend search patterns
_SEARCH_PATTERNS: dict[PackageManagerKind, list[str]] = {
    PackageManagerKind.APT: ["linux-image-"],
    PackageManagerKind.PACMAN: ["linux"],
    PackageManagerKind.DNF: ["kernel"],
    PackageManagerKind.ZYPPER: ["kernel-"],
    PackageManagerKind.APK: ["linux-"],
}

# Pacman kernel packages (well-known set; apt/dnf/zypper use search)
_PACMAN_KERNELS = [
    "linux",
    "linux-lts",
    "linux-zen",
    "linux-hardened",
    "linux-rt",
    "linux-rt-lts",
    "linux-cachyos",
    "linux-tkg-pds",
    "linux-xanmod",
    "linux-xanmod-lts",
]


class DistroNativeProvider(KernelProvider):
    @property
    def id(self) -> str:
        return "distro_native"

    @property
    def display_name(self) -> str:
        info = system_info()
        return f"{info.distro.name} Kernels"

    @property
    def family(self) -> KernelFamily:
        return KernelFamily.DISTRO

    @property
    def supported_arches(self) -> list[str]:
        return ["*"]  # Always available; arch is handled by the distro's repos

    def is_available(self) -> bool:
        return self._backend.is_available()

    # ------------------------------------------------------------------

    def fetch(self, arch: str, refresh: bool = False) -> list[KernelEntry]:
        if refresh:
            self._backend.refresh_cache()

        pm = system_info().package_manager
        running = system_info().running_kernel

        if pm == PackageManagerKind.PACMAN:
            return self._list_pacman(arch, running)
        elif pm == PackageManagerKind.APT:
            return self._list_apt(arch, running)
        elif pm == PackageManagerKind.DNF:
            return self._list_dnf(arch, running)
        elif pm == PackageManagerKind.ZYPPER:
            return self._list_zypper(arch, running)
        elif pm == PackageManagerKind.APK:
            return self._list_apk(arch, running)
        return []

    def install(self, entry: KernelEntry) -> Iterator[str]:
        pkg = entry.description or entry.display_name  # description stores pkg name
        yield f"Installing {pkg}...\n"
        rc, out, err = self._backend.install([pkg])
        if out:
            yield out
        if err:
            yield err
        if rc != 0:
            raise RuntimeError(f"Installation failed (exit {rc})")
        yield f"Kernel {entry.display_name} installed.\n"

    def remove(self, entry: KernelEntry, purge: bool = False) -> Iterator[str]:
        pkg = entry.description or entry.display_name
        yield f"Removing {pkg}...\n"
        rc, out, err = self._backend.remove([pkg], purge=purge)
        if out:
            yield out
        if err:
            yield err
        if rc != 0:
            raise RuntimeError(f"Removal failed (exit {rc})")
        yield f"Kernel {entry.display_name} removed.\n"

    # ------------------------------------------------------------------
    # Per-backend list implementations
    # ------------------------------------------------------------------

    def _list_apt(self, arch: str, running: str) -> list[KernelEntry]:
        rc, out, _ = self._backend._run(["apt-cache", "search", "--names-only", "linux-image"])
        if rc != 0:
            return []

        installed = set(self._backend.installed_packages("linux-image"))
        result: list[KernelEntry] = []

        for line in out.splitlines():
            pkg = line.split()[0] if line.split() else ""
            if not pkg.startswith("linux-image"):
                continue
            # Skip meta-packages without a version in the name
            ver_str = self._apt_pkg_version(pkg)
            if not ver_str:
                continue

            flavor = self._apt_flavor(pkg)
            is_inst = pkg in installed
            is_run = running and ver_str in running
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
                    flavor=flavor,
                    description=pkg,  # store pkg name for install/remove
                    status=status,
                    held=self._backend.is_held(pkg),
                )
            )

        return sorted(result, key=lambda e: e.version, reverse=True)

    def _list_pacman(self, arch: str, running: str) -> list[KernelEntry]:
        result: list[KernelEntry] = []
        for pkg in _PACMAN_KERNELS:
            # Check if available in repos
            rc, out, _ = self._backend._run(["pacman", "-Si", pkg])
            if rc != 0:
                continue
            ver_str = ""
            for line in out.splitlines():
                if line.startswith("Version"):
                    ver_str = line.split(":", 1)[1].strip()
                    break
            if not ver_str:
                continue

            is_inst = self._backend.is_installed(pkg)
            is_run = running and (pkg in running or ver_str in running)
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
                    description=pkg,
                    status=status,
                    held=self._backend.is_held(pkg),
                )
            )

        return sorted(result, key=lambda e: e.version, reverse=True)

    def _list_dnf(self, arch: str, running: str) -> list[KernelEntry]:
        rc, out, _ = self._backend._run(["dnf", "list", "--available", "kernel", "kernel-core"])
        if rc != 0:
            return []

        installed_rc, inst_out, _ = self._backend._run(
            ["rpm", "-qa", "--queryformat", "%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n", "kernel*"]
        )
        installed_set = set(inst_out.splitlines()) if installed_rc == 0 else set()

        result: list[KernelEntry] = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 2 or not parts[0].startswith("kernel"):
                continue
            ver_str = parts[1]
            pkg_id = f"{parts[0]}-{ver_str}"
            is_inst = any(pkg_id in p for p in installed_set)
            is_run = running and ver_str.split("-")[0] in running

            status = (
                KernelStatus.RUNNING
                if is_run
                else (KernelStatus.INSTALLED if is_inst else KernelStatus.AVAILABLE)
            )

            result.append(
                KernelEntry(
                    version=KernelVersion(ver_str),
                    family=self.family,
                    provider_id=self.id,
                    arch=arch,
                    flavor=parts[0],
                    description=parts[0],
                    status=status,
                )
            )

        return sorted(result, key=lambda e: e.version, reverse=True)

    def _list_zypper(self, arch: str, running: str) -> list[KernelEntry]:
        rc, out, _ = self._backend._run(["zypper", "search", "-t", "package", "kernel-"])
        if rc != 0:
            return []

        result: list[KernelEntry] = []
        for line in out.splitlines():
            if "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 5:
                continue
            pkg_name = parts[1]
            ver_str = parts[3]
            if not pkg_name.startswith("kernel-") or not ver_str:
                continue

            is_inst = self._backend.is_installed(pkg_name)
            is_run = running and ver_str in running
            status = (
                KernelStatus.RUNNING
                if is_run
                else (KernelStatus.INSTALLED if is_inst else KernelStatus.AVAILABLE)
            )

            result.append(
                KernelEntry(
                    version=KernelVersion(ver_str),
                    family=self.family,
                    provider_id=self.id,
                    arch=arch,
                    flavor=pkg_name,
                    description=pkg_name,
                    status=status,
                )
            )

        return sorted(result, key=lambda e: e.version, reverse=True)

    def _list_apk(self, arch: str, running: str) -> list[KernelEntry]:
        rc, out, _ = self._backend._run(["apk", "search", "linux-"])
        if rc != 0:
            return []

        result: list[KernelEntry] = []
        for line in out.splitlines():
            pkg = line.strip()
            if not pkg.startswith("linux-"):
                continue
            # apk search returns name-version
            m = re.match(r"^(linux-[a-z]+)-(\d[\d.]+.*)$", pkg)
            if not m:
                continue
            pkg_name, ver_str = m.group(1), m.group(2)
            is_inst = self._backend.is_installed(pkg_name)
            is_run = running and ver_str in running
            status = (
                KernelStatus.RUNNING
                if is_run
                else (KernelStatus.INSTALLED if is_inst else KernelStatus.AVAILABLE)
            )

            result.append(
                KernelEntry(
                    version=KernelVersion(ver_str),
                    family=self.family,
                    provider_id=self.id,
                    arch=arch,
                    flavor=pkg_name,
                    description=pkg_name,
                    status=status,
                )
            )

        return sorted(result, key=lambda e: e.version, reverse=True)

    # ------------------------------------------------------------------

    @staticmethod
    def _apt_pkg_version(pkg: str) -> str:
        """
        Extract version from apt package name like linux-image-6.8.0-45-generic.
        Returns '' for meta-packages like linux-image-generic.
        """
        m = re.search(r"(\d+\.\d+\.\d+[^\s-]*)", pkg)
        return m.group(1) if m else ""

    @staticmethod
    def _apt_flavor(pkg: str) -> str:
        """Extract flavor suffix from apt package name."""
        # linux-image-6.8.0-45-generic -> generic
        m = re.search(r"\d+\.\d+\.\d+[^-]*-\d+-(.+)$", pkg)
        return m.group(1) if m else "generic"
