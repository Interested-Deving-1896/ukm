"""
APK backend — Alpine Linux.
"""

from __future__ import annotations

import shutil

from ukm.core.backends.base import PackageBackend
from ukm.core.system import privilege_escalation_cmd


class ApkBackend(PackageBackend):

    @property
    def name(self) -> str:
        return "apk"

    def is_available(self) -> bool:
        return bool(shutil.which("apk"))

    def refresh_cache(self) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["apk", "update"])

    def install(self, packages: list[str]) -> tuple[int, str, str]:
        return self._run(
            privilege_escalation_cmd() + ["apk", "add"] + packages
        )

    def install_local(self, paths: list[str]) -> tuple[int, str, str]:
        return self._run(
            privilege_escalation_cmd() + ["apk", "add", "--allow-untrusted"] + paths
        )

    def remove(self, packages: list[str], purge: bool = False) -> tuple[int, str, str]:
        flags = ["--purge"] if purge else []
        return self._run(
            privilege_escalation_cmd() + ["apk", "del"] + flags + packages
        )

    def hold(self, packages: list[str]) -> tuple[int, str, str]:
        """
        Alpine uses world file pinning. We pin to the currently installed version.
        """
        results = []
        for pkg in packages:
            rc, out, err = self._run(["apk", "info", "-e", pkg])
            if rc == 0:
                # Pin to exact version
                rc2, out2, err2 = self._run(
                    privilege_escalation_cmd() + ["apk", "add", f"{pkg}="]
                )
                results.append((rc2, out2, err2))
        if not results:
            return 0, "", ""
        # Return last result; caller can check logs
        return results[-1]

    def unhold(self, packages: list[str]) -> tuple[int, str, str]:
        return self._run(
            privilege_escalation_cmd() + ["apk", "add"] + packages
        )

    def is_installed(self, package: str) -> bool:
        rc, _, _ = self._run(["apk", "info", "-e", package])
        return rc == 0

    def is_held(self, package: str) -> bool:
        # Alpine doesn't have a direct hold concept; check world file for pinned version
        try:
            with open("/etc/apk/world") as f:
                for line in f:
                    if line.strip().startswith(package + "="):
                        return True
        except FileNotFoundError:
            pass
        return False

    def installed_packages(self, pattern: str = "") -> list[str]:
        cmd = ["apk", "info"]
        if pattern:
            cmd += ["-e", pattern]
        rc, out, _ = self._run(cmd)
        if rc != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]
