"""
APT/dpkg backend — Debian, Ubuntu, Mint, Pop!_OS, Kali, etc.
"""

from __future__ import annotations

import shutil

from ukm.core.backends.base import PackageBackend
from ukm.core.system import privilege_escalation_cmd


class AptBackend(PackageBackend):
    @property
    def name(self) -> str:
        return "apt"

    def is_available(self) -> bool:
        return bool(shutil.which("apt-get"))

    def refresh_cache(self) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["apt-get", "update", "-q"])

    def install(self, packages: list[str]) -> tuple[int, str, str]:
        return self._run(
            privilege_escalation_cmd()
            + [
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
            ]
            + packages,
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )

    def install_local(self, paths: list[str]) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["dpkg", "-i"] + paths)

    def remove(self, packages: list[str], purge: bool = False) -> tuple[int, str, str]:
        verb = "purge" if purge else "remove"
        return self._run(privilege_escalation_cmd() + ["apt-get", verb, "-y"] + packages)

    def hold(self, packages: list[str]) -> tuple[int, str, str]:
        cmd = privilege_escalation_cmd() + ["apt-mark", "hold"] + packages
        return self._run(cmd)

    def unhold(self, packages: list[str]) -> tuple[int, str, str]:
        return self._run(privilege_escalation_cmd() + ["apt-mark", "unhold"] + packages)

    def is_installed(self, package: str) -> bool:
        rc, out, _ = self._run(["dpkg-query", "-W", "-f=${Status}", package])
        return rc == 0 and "install ok installed" in out

    def is_held(self, package: str) -> bool:
        rc, out, _ = self._run(["apt-mark", "showhold"])
        return rc == 0 and package in out.splitlines()

    def installed_packages(self, pattern: str = "") -> list[str]:
        rc, out, _ = self._run(
            ["dpkg-query", "-W", "-f=${Package}\n"] + ([f"*{pattern}*"] if pattern else [])
        )
        if rc != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    def add_repository(self, repo_line: str, key_url: str = "") -> tuple[int, str, str]:
        """
        Add an apt repository and optionally import its signing key.
        Used by XanMod and Liquorix providers.
        """
        import os
        import tempfile

        priv = privilege_escalation_cmd()

        if key_url:
            rc, out, err = self._run(
                ["curl", "-fsSL", key_url],
            )
            if rc != 0:
                return rc, out, err
            key_data = out
            with tempfile.NamedTemporaryFile(suffix=".asc", delete=False, mode="w") as f:
                f.write(key_data)
                key_path = f.name
            rc, out, err = self._run(
                priv
                + [
                    "gpg",
                    "--dearmor",
                    "-o",
                    f"/usr/share/keyrings/ukm-{repo_line.split()[0]}.gpg",
                    key_path,
                ]
            )
            os.unlink(key_path)
            if rc != 0:
                return rc, out, err

        # Write sources list entry
        sources_file = f"/etc/apt/sources.list.d/ukm-{repo_line.split()[0]}.list"
        rc, out, err = self._run(
            priv + ["tee", sources_file],
            input=repo_line + "\n",
        )
        return rc, out, err
