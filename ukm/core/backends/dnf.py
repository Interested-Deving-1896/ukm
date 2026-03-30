"""
DNF backend — Fedora, RHEL, AlmaLinux, Rocky, Nobara, Oracle, etc.
"""

from __future__ import annotations

import shutil

from ukm.core.backends.base import PackageBackend
from ukm.core.system import privilege_escalation_cmd


class DnfBackend(PackageBackend):
    @property
    def name(self) -> str:
        return "dnf"

    def is_available(self) -> bool:
        return bool(shutil.which("dnf"))

    def refresh_cache(self) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["dnf", "makecache", "-q", "-y"])

    def install(self, packages: list[str]) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["dnf", "install", "-y"] + packages)

    def install_local(self, paths: list[str]) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["dnf", "install", "-y"] + paths)

    def remove(self, packages: list[str], purge: bool = False) -> tuple[int, str, str]:
        # DNF remove always cleans config; purge flag is a no-op here
        return self._run(privilege_escalation_cmd() + ["dnf", "remove", "-y"] + packages)

    def hold(self, packages: list[str]) -> tuple[int, str, str]:
        """Use dnf versionlock to pin packages."""
        return self._run(privilege_escalation_cmd() + ["dnf", "versionlock", "add"] + packages)

    def unhold(self, packages: list[str]) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["dnf", "versionlock", "delete"] + packages)

    def is_installed(self, package: str) -> bool:
        rc, _, _ = self._run(["rpm", "-q", package])
        return rc == 0

    def is_held(self, package: str) -> bool:
        rc, out, _ = self._run(["dnf", "versionlock", "list"])
        return rc == 0 and package in out

    def installed_packages(self, pattern: str = "") -> list[str]:
        cmd = ["rpm", "-qa", "--queryformat", "%{NAME}\n"]
        if pattern:
            cmd += [f"*{pattern}*"]
        rc, out, _ = self._run(cmd)
        if rc != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]
