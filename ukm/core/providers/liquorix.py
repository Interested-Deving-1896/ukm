"""
Liquorix kernel provider.

Liquorix is a low-latency kernel optimised for desktop and gaming workloads,
maintained by Steven Barrett (damentz). It publishes x86-64 .deb packages.

Repository: https://liquorix.net
"""

from __future__ import annotations

from collections.abc import Iterator

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion
from ukm.core.providers.base import KernelProvider
from ukm.core.system import system_info

_LIQUORIX_INSTALL_SCRIPT = "https://liquorix.net/install-liquorix.sh"
_SUPPORTED_ARCHES = ["amd64"]


class LiquorixProvider(KernelProvider):
    @property
    def id(self) -> str:
        return "liquorix"

    @property
    def display_name(self) -> str:
        return "Liquorix"

    @property
    def family(self) -> KernelFamily:
        return KernelFamily.LIQUORIX

    @property
    def supported_arches(self) -> list[str]:
        return _SUPPORTED_ARCHES

    def is_available(self) -> bool:
        import shutil

        return bool(shutil.which("apt-get")) and system_info().arch == "amd64"

    def availability_reason(self) -> str:
        return (
            "Liquorix kernels are only available for x86-64 (amd64) systems "
            "running a Debian/Ubuntu-based distribution."
        )

    def is_repo_configured(self) -> bool:
        rc, out, _ = self._backend._run(["apt-cache", "search", "linux-image-liquorix"])
        return rc == 0 and "liquorix" in out.lower()

    def setup_repo(self) -> Iterator[str]:
        """
        Liquorix provides an official install script that adds the repo and key.
        We download and execute it with privilege escalation.
        """
        import os
        import tempfile
        import urllib.request

        from ukm.core.system import privilege_escalation_cmd

        yield "Downloading Liquorix install script...\n"
        with tempfile.NamedTemporaryFile(suffix=".sh", delete=False, mode="wb") as f:
            try:
                with urllib.request.urlopen(_LIQUORIX_INSTALL_SCRIPT, timeout=15) as r:
                    f.write(r.read())
                script_path = f.name
            except Exception as e:
                raise RuntimeError(f"Failed to download Liquorix install script: {e}") from e

        os.chmod(script_path, 0o755)
        yield "Running Liquorix install script...\n"
        yield from self._backend.stream(privilege_escalation_cmd() + ["bash", script_path])
        os.unlink(script_path)
        yield "Liquorix repository configured.\n"

    # ------------------------------------------------------------------

    def fetch(self, arch: str, refresh: bool = False) -> list[KernelEntry]:
        if arch not in _SUPPORTED_ARCHES:
            return []

        if refresh:
            self._backend.refresh_cache()

        rc, out, _ = self._backend._run(
            ["apt-cache", "search", "--names-only", "linux-image-liquorix"]
        )
        if rc != 0:
            return []

        installed_raw = self._backend.installed_packages("linux-image-liquorix")
        running = system_info().running_kernel
        result: list[KernelEntry] = []

        for line in out.splitlines():
            pkg_name = line.split()[0] if line.split() else ""
            if "liquorix" not in pkg_name:
                continue

            ver_str = self._version_from_apt(pkg_name)
            if not ver_str:
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

            result.append(
                KernelEntry(
                    version=KernelVersion(ver_str),
                    family=self.family,
                    provider_id=self.id,
                    arch=arch,
                    flavor="liquorix",
                    description="Low-latency desktop/gaming kernel",
                    status=status,
                    held=self._backend.is_held(pkg_name),
                )
            )

        return sorted(result, key=lambda e: e.version, reverse=True)

    def install(self, entry: KernelEntry) -> Iterator[str]:
        from ukm.core.system import privilege_escalation_cmd

        ver = str(entry.version)
        image_pkg = "linux-image-liquorix-amd64"
        headers_pkg = "linux-headers-liquorix-amd64"
        yield f"Installing Liquorix kernel {ver}...\n"
        cmd = privilege_escalation_cmd() + [
            "apt-get",
            "install",
            "-y",
            "--no-install-recommends",
            image_pkg,
            headers_pkg,
        ]
        rc = 0
        for line in self._backend.stream(cmd):
            yield line
            if "E:" in line or "error" in line.lower():
                rc = 1
        if rc != 0:
            raise RuntimeError(f"Installation failed for Liquorix {ver}")
        yield f"Liquorix kernel {ver} installed.\n"

    def remove(self, entry: KernelEntry, purge: bool = False) -> Iterator[str]:
        ver = str(entry.version)
        yield f"Removing Liquorix kernel {ver}...\n"
        pkgs = [
            p for p in self._backend.installed_packages("linux-") if "liquorix" in p and ver in p
        ]
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
        yield f"Liquorix kernel {ver} removed.\n"

    def hold(self, entry: KernelEntry) -> tuple[int, str, str]:
        pkgs = [
            p
            for p in self._backend.installed_packages("linux-")
            if "liquorix" in p and str(entry.version) in p
        ]
        return self._backend.hold(pkgs) if pkgs else (0, "Nothing to hold.", "")

    def unhold(self, entry: KernelEntry) -> tuple[int, str, str]:
        pkgs = [
            p
            for p in self._backend.installed_packages("linux-")
            if "liquorix" in p and str(entry.version) in p
        ]
        return self._backend.unhold(pkgs) if pkgs else (0, "Nothing to unhold.", "")

    def _version_from_apt(self, pkg: str) -> str:
        rc, out, _ = self._backend._run(["apt-cache", "show", pkg])
        if rc != 0:
            return ""
        for line in out.splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
        return ""
