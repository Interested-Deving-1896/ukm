"""
Zypper backend — openSUSE Leap, openSUSE Tumbleweed, SLES.
"""

from __future__ import annotations

import shutil

from ukm.core.backends.base import PackageBackend
from ukm.core.system import privilege_escalation_cmd


class ZypperBackend(PackageBackend):
    @property
    def name(self) -> str:
        return "zypper"

    def is_available(self) -> bool:
        return bool(shutil.which("zypper"))

    def refresh_cache(self) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["zypper", "refresh", "-q"])

    def install(self, packages: list[str]) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["zypper", "install", "-y"] + packages)

    def install_local(self, paths: list[str]) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["zypper", "install", "-y"] + paths)

    def remove(self, packages: list[str], purge: bool = False) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["zypper", "remove", "-y"] + packages)

    def hold(self, packages: list[str]) -> tuple[int, str, str]:
        """Lock packages using zypper addlock."""
        return self._run(privilege_escalation_cmd() + ["zypper", "addlock"] + packages)

    def unhold(self, packages: list[str]) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["zypper", "removelock"] + packages)

    def is_installed(self, package: str) -> bool:
        rc, _, _ = self._run(["rpm", "-q", package])
        return rc == 0

    def is_held(self, package: str) -> bool:
        rc, out, _ = self._run(["zypper", "locks"])
        return rc == 0 and package in out

    def installed_packages(self, pattern: str = "") -> list[str]:
        cmd = ["rpm", "-qa", "--queryformat", "%{NAME}\n"]
        rc, out, _ = self._run(cmd)
        if rc != 0:
            return []
        pkgs = [line.strip() for line in out.splitlines() if line.strip()]
        if pattern:
            pkgs = [p for p in pkgs if pattern.lower() in p.lower()]
        return pkgs
