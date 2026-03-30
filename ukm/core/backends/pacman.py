"""
Pacman backend — Arch, Manjaro, EndeavourOS, CachyOS, Artix, etc.
"""

from __future__ import annotations

import shutil

from ukm.core.backends.base import PackageBackend
from ukm.core.system import privilege_escalation_cmd


class PacmanBackend(PackageBackend):
    @property
    def name(self) -> str:
        return "pacman"

    def is_available(self) -> bool:
        return bool(shutil.which("pacman"))

    def refresh_cache(self) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["pacman", "-Sy", "--noconfirm"])

    def install(self, packages: list[str]) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["pacman", "-S", "--noconfirm"] + packages)

    def install_local(self, paths: list[str]) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["pacman", "-U", "--noconfirm"] + paths)

    def remove(self, packages: list[str], purge: bool = False) -> tuple[int, str, str]:
        flags = ["-Rns"] if purge else ["-R"]
        return self._run(
            privilege_escalation_cmd() + ["pacman"] + flags + ["--noconfirm"] + packages
        )

    def hold(self, packages: list[str]) -> tuple[int, str, str]:
        """
        Pacman doesn't have a native hold. We add packages to IgnorePkg in
        /etc/pacman.conf. This is a best-effort implementation.
        """
        return self._edit_ignore_pkg(packages, add=True)

    def unhold(self, packages: list[str]) -> tuple[int, str, str]:
        return self._edit_ignore_pkg(packages, add=False)

    def is_installed(self, package: str) -> bool:
        rc, _, _ = self._run(["pacman", "-Q", package])
        return rc == 0

    def is_held(self, package: str) -> bool:
        try:
            with open("/etc/pacman.conf") as f:
                for line in f:
                    if line.strip().startswith("IgnorePkg"):
                        return package in line
        except FileNotFoundError:
            pass
        return False

    def installed_packages(self, pattern: str = "") -> list[str]:
        cmd = ["pacman", "-Qq"]
        if pattern:
            cmd += [pattern]
        rc, out, _ = self._run(cmd)
        if rc != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    # ------------------------------------------------------------------

    def _edit_ignore_pkg(self, packages: list[str], add: bool) -> tuple[int, str, str]:
        conf = "/etc/pacman.conf"
        try:
            with open(conf) as f:
                lines = f.readlines()
        except FileNotFoundError:
            return 1, "", f"{conf} not found"

        new_lines = []
        found = False
        for line in lines:
            if line.strip().startswith("IgnorePkg"):
                found = True
                current = set(line.split("=", 1)[1].strip().split())
                if add:
                    current.update(packages)
                else:
                    current -= set(packages)
                new_lines.append(f"IgnorePkg = {' '.join(sorted(current))}\n")
            else:
                new_lines.append(line)

        if not found and add:
            new_lines.append(f"\nIgnorePkg = {' '.join(packages)}\n")

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".conf") as f:
            f.writelines(new_lines)
            tmp = f.name

        rc, out, err = self._run(privilege_escalation_cmd() + ["cp", tmp, conf])
        os.unlink(tmp)
        return rc, out, err
