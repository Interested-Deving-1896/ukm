"""
Portage backend — Gentoo Linux.

Supports two modes:
  - Package mode: install/remove kernel packages via emerge (sys-kernel/*)
  - Source mode:  configure and compile kernels via genkernel or make directly

Source-mode operations are long-running and should always be streamed
(use backend.stream(...)) rather than captured.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ukm.core.backends.base import PackageBackend
from ukm.core.system import privilege_escalation_cmd


class PortageBackend(PackageBackend):

    @property
    def name(self) -> str:
        return "portage"

    def is_available(self) -> bool:
        return bool(shutil.which("emerge"))

    # ------------------------------------------------------------------
    # PackageBackend interface
    # ------------------------------------------------------------------

    def refresh_cache(self) -> tuple[int, str, str]:
        """Sync the portage tree (emerge --sync or emaint sync)."""
        if shutil.which("emaint"):
            return self._run(privilege_escalation_cmd() + ["emaint", "sync", "-a"])
        return self._run(privilege_escalation_cmd() + ["emerge", "--sync"])

    def install(self, packages: list[str]) -> tuple[int, str, str]:
        return self._run(
            privilege_escalation_cmd() + [
                "emerge", "--ask=n", "--quiet-build", "--noreplace",
            ] + packages
        )

    def install_local(self, paths: list[str]) -> tuple[int, str, str]:
        # Portage doesn't install arbitrary local tarballs the same way;
        # the closest is creating a local overlay. We surface a clear error.
        return (
            1,
            "",
            "Portage does not support direct local package installation. "
            "Use a local overlay or layman/eselect-repository instead.",
        )

    def remove(self, packages: list[str], purge: bool = False) -> tuple[int, str, str]:
        flags = ["--depclean"] if purge else ["--unmerge"]
        return self._run(
            privilege_escalation_cmd() + ["emerge"] + flags + ["--ask=n"] + packages
        )

    def hold(self, packages: list[str]) -> tuple[int, str, str]:
        """
        Pin packages by writing a =/category/package-version atom to
        /etc/portage/package.mask for upgrades, and adding them to
        /etc/portage/package.unmask so they stay installed.

        Simpler approach: write a ~arch keyword mask so the package
        won't be upgraded beyond the current version.
        """
        lines = []
        for pkg in packages:
            ver = self._installed_version(pkg)
            if ver:
                lines.append(f">{pkg}-{ver}\n")
            else:
                lines.append(f"{pkg}\n")

        mask_dir = Path("/etc/portage/package.mask")
        mask_file = mask_dir / "ukm-held" if mask_dir.is_dir() else mask_dir
        try:
            existing = mask_file.read_text() if mask_file.exists() else ""
            new_content = existing + "".join(lines)
            import os
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
                f.write(new_content)
                tmp = f.name
            rc, out, err = self._run(
                privilege_escalation_cmd() + ["cp", tmp, str(mask_file)]
            )
            os.unlink(tmp)
            return rc, out, err
        except Exception as e:
            return 1, "", str(e)

    def unhold(self, packages: list[str]) -> tuple[int, str, str]:
        mask_dir = Path("/etc/portage/package.mask")
        mask_file = mask_dir / "ukm-held" if mask_dir.is_dir() else mask_dir
        if not mask_file.exists():
            return 0, "No held packages.", ""
        try:
            lines = mask_file.read_text().splitlines(keepends=True)
            new_lines = [
                line for line in lines
                if not any(pkg in line for pkg in packages)
            ]
            import os
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
                f.writelines(new_lines)
                tmp = f.name
            rc, out, err = self._run(
                privilege_escalation_cmd() + ["cp", tmp, str(mask_file)]
            )
            os.unlink(tmp)
            return rc, out, err
        except Exception as e:
            return 1, "", str(e)

    def is_installed(self, package: str) -> bool:
        rc, _, _ = self._run(["equery", "list", "-i", package])
        return rc == 0

    def is_held(self, package: str) -> bool:
        mask_dir = Path("/etc/portage/package.mask")
        mask_file = mask_dir / "ukm-held" if mask_dir.is_dir() else mask_dir
        if not mask_file.exists():
            return False
        return package in mask_file.read_text()

    def installed_packages(self, pattern: str = "") -> list[str]:
        cmd = ["equery", "list", "-i", f"*{pattern}*" if pattern else "*"]
        rc, out, _ = self._run(cmd)
        if rc != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    # ------------------------------------------------------------------
    # Gentoo-specific: source compilation
    # ------------------------------------------------------------------

    def has_genkernel(self) -> bool:
        return bool(shutil.which("genkernel"))

    def has_eselect_kernel(self) -> bool:
        rc, _, _ = self._run(["eselect", "kernel", "list"])
        return rc == 0

    def list_kernel_sources(self) -> list[str]:
        """Return installed kernel source directories under /usr/src/."""
        src = Path("/usr/src")
        if not src.exists():
            return []
        return sorted(
            str(p) for p in src.iterdir()
            if p.is_dir() and p.name.startswith("linux-")
        )

    def set_active_source(self, src_path: str) -> tuple[int, str, str]:
        """Point /usr/src/linux symlink at the given source tree."""
        return self._run(
            privilege_escalation_cmd() + ["ln", "-sfn", src_path, "/usr/src/linux"]
        )

    def configure_kernel(self, src_path: str, target: str = "menuconfig") -> list[str]:
        """
        Return the command to launch kernel configuration.
        Caller is responsible for running this in a terminal (it is interactive).
        Supported targets: menuconfig, nconfig, xconfig, gconfig, oldconfig,
                           olddefconfig, defconfig, allmodconfig.
        """
        return privilege_escalation_cmd() + ["make", "-C", src_path, target]

    def compile_kernel_genkernel(
        self,
        src_path: str,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """
        Return the genkernel command to compile and install the kernel.
        Caller streams this command for live output.
        """
        cmd = privilege_escalation_cmd() + [
            "genkernel",
            "--kernel-dir", src_path,
            "--install",
            "--bootloader=grub2",
        ]
        if extra_args:
            cmd += extra_args
        cmd.append("all")
        return cmd

    def compile_kernel_make(
        self,
        src_path: str,
        jobs: int = 0,
        targets: list[str] | None = None,
    ) -> list[str]:
        """
        Return the make command to compile the kernel.
        jobs=0 means auto-detect (nproc).
        """
        import os
        j = jobs or os.cpu_count() or 1
        cmd = privilege_escalation_cmd() + [
            "make", "-C", src_path, f"-j{j}",
        ] + (targets or ["bzImage", "modules"])
        return cmd

    def install_kernel_make(self, src_path: str) -> list[str]:
        """Return the make install + modules_install command."""
        return privilege_escalation_cmd() + [
            "make", "-C", src_path, "modules_install", "install"
        ]

    def update_bootloader(self) -> tuple[int, str, str]:
        """Regenerate grub config after a new kernel is installed."""
        if shutil.which("grub-mkconfig"):
            return self._run(
                privilege_escalation_cmd() + [
                    "grub-mkconfig", "-o", "/boot/grub/grub.cfg"
                ]
            )
        if shutil.which("grub2-mkconfig"):
            return self._run(
                privilege_escalation_cmd() + [
                    "grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"
                ]
            )
        return 1, "", "No grub-mkconfig found. Update your bootloader manually."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _installed_version(self, package: str) -> str:
        """Return the installed version string for a package, or ''."""
        rc, out, _ = self._run(["equery", "list", "-i", "--format=$version", package])
        if rc == 0 and out.strip():
            return out.strip().splitlines()[0]
        return ""
