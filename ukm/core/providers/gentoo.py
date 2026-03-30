"""
Gentoo kernel provider.

Supports two modes, both exposed through the same provider interface:

  Package mode  — install/remove sys-kernel/* packages via emerge.
                  Covers genkernel, gentoo-kernel, gentoo-kernel-bin,
                  vanilla-kernel, rt-sources, zen-sources, etc.

  Source mode   — configure and compile a kernel from installed sources.
                  Uses genkernel (if available) or raw make.
                  Source-mode operations yield log lines and are meant to
                  be streamed in the GUI's log panel or printed in the CLI.

The GUI exposes source-mode via a dedicated "Compile" button that opens
a compilation dialog; the CLI exposes it via `ukm gentoo compile`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion
from ukm.core.providers.base import KernelProvider
from ukm.core.backends.portage import PortageBackend

# Well-known Gentoo kernel packages in sys-kernel/
_GENTOO_KERNEL_PACKAGES = [
    "sys-kernel/gentoo-kernel",
    "sys-kernel/gentoo-kernel-bin",
    "sys-kernel/vanilla-kernel",
    "sys-kernel/gentoo-sources",
    "sys-kernel/vanilla-sources",
    "sys-kernel/rt-sources",
    "sys-kernel/zen-sources",
    "sys-kernel/hardened-sources",
    "sys-kernel/pf-sources",
    "sys-kernel/ck-sources",
    "sys-kernel/git-sources",
    "sys-kernel/raspberrypi-sources",
    "sys-kernel/mips-sources",
    "sys-kernel/arm-sources",
]

# Descriptions for display
_PKG_DESCRIPTIONS = {
    "gentoo-kernel":     "Gentoo kernel with genkernel (binary config)",
    "gentoo-kernel-bin": "Gentoo kernel pre-compiled binary",
    "vanilla-kernel":    "Vanilla upstream kernel (binary config)",
    "gentoo-sources":    "Gentoo-patched kernel sources (compile yourself)",
    "vanilla-sources":   "Vanilla upstream kernel sources",
    "rt-sources":        "PREEMPT_RT real-time kernel sources",
    "zen-sources":       "Zen kernel sources",
    "hardened-sources":  "Hardened kernel sources",
    "pf-sources":        "pf-kernel sources (BFQ + UKSM + ...)",
    "ck-sources":        "Con Kolivas patchset sources",
    "git-sources":       "Latest upstream git kernel sources",
    "raspberrypi-sources": "Raspberry Pi kernel sources",
    "mips-sources":      "MIPS architecture kernel sources",
    "arm-sources":       "ARM architecture kernel sources",
}


class GentooProvider(KernelProvider):

    def __init__(self, backend: PortageBackend) -> None:
        if not isinstance(backend, PortageBackend):
            raise TypeError("GentooProvider requires a PortageBackend")
        super().__init__(backend)
        self._portage: PortageBackend = backend

    @property
    def id(self) -> str:
        return "gentoo"

    @property
    def display_name(self) -> str:
        return "Gentoo"

    @property
    def family(self) -> KernelFamily:
        return KernelFamily.GENTOO

    @property
    def supported_arches(self) -> list[str]:
        # Gentoo supports everything the kernel supports
        return ["*"]

    def is_available(self) -> bool:
        return self._portage.is_available()

    def availability_reason(self) -> str:
        return "Gentoo provider requires emerge (Portage package manager)."

    # ------------------------------------------------------------------
    # list()
    # ------------------------------------------------------------------

    def list(self, arch: str, refresh: bool = False) -> list[KernelEntry]:
        if refresh:
            self._portage.refresh_cache()

        result: list[KernelEntry] = []

        # --- Package-mode entries (emerge-installable) ---
        for atom in _GENTOO_KERNEL_PACKAGES:
            category, pkg_name = atom.split("/")
            versions = self._available_versions(atom)
            installed_versions = self._installed_versions(atom)
            running = self._running_version()

            for ver_str in versions:
                is_inst = ver_str in installed_versions
                is_run = running and ver_str in running
                status = KernelStatus.RUNNING if is_run else (
                    KernelStatus.INSTALLED if is_inst else KernelStatus.AVAILABLE
                )
                if self._portage.is_held(atom):
                    status = KernelStatus.HELD

                result.append(KernelEntry(
                    version=KernelVersion(ver_str),
                    family=self.family,
                    provider_id=self.id,
                    arch=arch,
                    flavor=pkg_name,
                    description=_PKG_DESCRIPTIONS.get(pkg_name, atom),
                    status=status,
                    held=self._portage.is_held(atom),
                    source_url=f"https://packages.gentoo.org/packages/{atom}",
                ))

        # --- Source-mode entries (already-installed source trees) ---
        for src_path in self._portage.list_kernel_sources():
            ver_str = self._version_from_src_path(src_path)
            if not ver_str:
                continue
            # Check if a compiled kernel exists for this source
            is_compiled = self._is_compiled(src_path)
            status = KernelStatus.INSTALLED if is_compiled else KernelStatus.AVAILABLE

            result.append(KernelEntry(
                version=KernelVersion(ver_str),
                family=self.family,
                provider_id=self.id,
                arch=arch,
                flavor="source",
                description=f"Source tree: {src_path}",
                status=status,
                source_url=src_path,
                notes="Source tree — use 'Compile' to build",
            ))

        return sorted(result, key=lambda e: e.version, reverse=True)

    # ------------------------------------------------------------------
    # install() — package mode
    # ------------------------------------------------------------------

    def install(self, entry: KernelEntry) -> Iterator[str]:
        if entry.flavor == "source":
            # Source entries are not installed via emerge; direct user to compile
            yield (
                f"Source tree {entry.source_url} is already present.\n"
                "Use 'Compile' to configure and build this kernel.\n"
            )
            return

        atom = f"sys-kernel/{entry.flavor}"
        ver = str(entry.version)
        versioned_atom = f"={atom}-{ver}"

        yield f"Installing {versioned_atom} via emerge...\n"
        from ukm.core.system import privilege_escalation_cmd
        cmd = privilege_escalation_cmd() + [
            "emerge", "--ask=n", "--quiet-build", "--noreplace", versioned_atom
        ]
        yield from self._portage.stream(cmd)

        # Confirm installation succeeded
        rc, out, err = self._portage._run(["equery", "list", "-i", versioned_atom])
        if rc != 0:
            raise RuntimeError(f"emerge failed — {versioned_atom} not found after install")
        yield f"Kernel {entry.display_name} installed.\n"

    # ------------------------------------------------------------------
    # remove() — package mode
    # ------------------------------------------------------------------

    def remove(self, entry: KernelEntry, purge: bool = False) -> Iterator[str]:
        if entry.flavor == "source":
            yield "Source trees must be removed manually or via emerge --unmerge.\n"
            return

        atom = f"sys-kernel/{entry.flavor}"
        ver = str(entry.version)
        versioned_atom = f"={atom}-{ver}"

        yield f"Removing {versioned_atom}...\n"
        rc, out, err = self._portage.remove([versioned_atom], purge=purge)
        if out:
            yield out
        if err:
            yield err
        if rc != 0:
            raise RuntimeError(f"emerge --unmerge failed (exit {rc})")
        yield f"Kernel {entry.display_name} removed.\n"

    # ------------------------------------------------------------------
    # Source-mode compilation
    # ------------------------------------------------------------------

    def configure_cmd(self, src_path: str, target: str = "menuconfig") -> list[str]:
        """
        Return the command to launch kernel configuration interactively.
        The caller must run this in a terminal emulator.
        """
        return self._portage.configure_kernel(src_path, target)

    def compile(
        self,
        src_path: str,
        use_genkernel: bool = True,
        jobs: int = 0,
        extra_args: list[str] | None = None,
    ) -> Iterator[str]:
        """
        Compile and install a kernel from source. Yields log lines.

        use_genkernel=True  → use genkernel (handles initramfs + bootloader)
        use_genkernel=False → raw make bzImage + modules + install
        """
        yield f"Starting kernel compilation in {src_path}...\n"

        if use_genkernel and self._portage.has_genkernel():
            cmd = self._portage.compile_kernel_genkernel(src_path, extra_args)
            yield f"Using genkernel: {' '.join(cmd)}\n"
        else:
            if use_genkernel:
                yield "genkernel not found, falling back to make.\n"
            cmd = self._portage.compile_kernel_make(src_path, jobs=jobs)
            yield f"Using make: {' '.join(cmd)}\n"

        for line in self._portage.stream(cmd):
            yield line

        if not use_genkernel or not self._portage.has_genkernel():
            yield "Installing kernel and modules...\n"
            install_cmd = self._portage.install_kernel_make(src_path)
            for line in self._portage.stream(install_cmd):
                yield line

            yield "Updating bootloader...\n"
            rc, out, err = self._portage.update_bootloader()
            if out:
                yield out
            if err:
                yield err
            if rc != 0:
                yield f"⚠ Bootloader update failed (exit {rc}). Update manually.\n"

        yield "Compilation complete.\n"

    def set_active_source(self, src_path: str) -> tuple[int, str, str]:
        """Point /usr/src/linux at the given source tree."""
        return self._portage.set_active_source(src_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _available_versions(self, atom: str) -> list[str]:
        """Query portage for available versions of an atom."""
        rc, out, _ = self._portage._run(
            ["emerge", "--search", f"^{atom}$"]
        )
        if rc != 0:
            return []
        versions = re.findall(r"Latest version available:\s+(\S+)", out)
        return versions

    def _installed_versions(self, atom: str) -> list[str]:
        """Return installed versions of an atom."""
        rc, out, _ = self._portage._run(
            ["equery", "list", "-i", "--format=$version", atom]
        )
        if rc != 0:
            return []
        return [v.strip() for v in out.splitlines() if v.strip()]

    def _running_version(self) -> str:
        from ukm.core.system import system_info
        return system_info().running_kernel

    @staticmethod
    def _version_from_src_path(src_path: str) -> str:
        """Extract version from /usr/src/linux-6.9.0-gentoo."""
        m = re.search(r"linux-(\d+\.\d+[\d.]*[^\s/]*)", src_path)
        return m.group(1) if m else ""

    @staticmethod
    def _is_compiled(src_path: str) -> bool:
        """Check if a vmlinuz or bzImage exists for this source tree."""
        src = Path(src_path)
        if (src / "arch" / "x86" / "boot" / "bzImage").exists():
            return True
        stem = src.name.replace("linux-", "")
        return any(Path("/boot").glob(f"vmlinuz-*{stem}*"))
