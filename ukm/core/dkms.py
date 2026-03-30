"""
DKMS (Dynamic Kernel Module Support) integration.

When a new kernel is installed or an old one removed, DKMS modules
(NVIDIA, VirtualBox, ZFS, etc.) need to be rebuilt or cleaned up for
that kernel version. This module handles that automatically.

Lifecycle:
  - After install:  dkms autoinstall -k <version>
  - After remove:   dkms remove --all -k <version>  (best-effort)
  - Status query:   dkms status

The KernelManager calls dkms_autoinstall() / dkms_remove() after each
successful kernel install/remove operation.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass
class DkmsModule:
    name: str
    version: str
    kernel: str
    arch: str
    status: str  # "installed", "built", "added", "uninstalled", "broken"


def is_available() -> bool:
    """Return True if dkms is installed on this system."""
    return bool(shutil.which("dkms"))


def status() -> list[DkmsModule]:
    """
    Return all DKMS modules and their status across all installed kernels.
    Parses `dkms status` output.
    """
    if not is_available():
        return []

    result = subprocess.run(
        ["dkms", "status"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return []

    modules: list[DkmsModule] = []
    # Modern dkms status format:
    #   nvidia/550.54.14, 6.8.0-45-generic, x86_64: installed
    # Legacy format:
    #   nvidia, 550.54.14, 6.8.0-45-generic, x86_64: installed
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^([^/,]+)[/,]\s*([^,]+),\s*([^,]+),\s*([^:]+):\s*(.+)$", line)
        if m:
            modules.append(
                DkmsModule(
                    name=m.group(1).strip(),
                    version=m.group(2).strip(),
                    kernel=m.group(3).strip(),
                    arch=m.group(4).strip(),
                    status=m.group(5).strip(),
                )
            )
    return modules


def modules_for_kernel(kernel_version: str) -> list[DkmsModule]:
    """Return all DKMS modules registered for a specific kernel version."""
    return [m for m in status() if kernel_version in m.kernel]


def autoinstall(kernel_version: str) -> Iterator[str]:
    """
    Run `dkms autoinstall` for the given kernel version.
    Yields log lines. Raises RuntimeError on failure.

    This rebuilds all registered DKMS modules for the new kernel.
    Called automatically after a kernel is installed.
    """
    if not is_available():
        yield "dkms not found — skipping DKMS module rebuild.\n"
        yield "Install dkms to automatically rebuild kernel modules (NVIDIA, ZFS, etc.).\n"
        return

    mods = status()
    if not mods:
        yield "No DKMS modules registered — nothing to rebuild.\n"
        return

    yield f"Rebuilding DKMS modules for kernel {kernel_version}...\n"

    from ukm.core.system import privilege_escalation_cmd

    cmd = privilege_escalation_cmd() + ["dkms", "autoinstall", "-k", kernel_version]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None
    failed = False
    for line in proc.stdout:
        yield line
        if "Error!" in line or "FAILED" in line:
            failed = True
    proc.wait()

    if proc.returncode != 0 or failed:
        yield f"⚠ DKMS autoinstall finished with errors for kernel {kernel_version}.\n"
        yield "  Some modules may not work. Check 'dkms status' for details.\n"
    else:
        yield f"✓ DKMS modules rebuilt for kernel {kernel_version}.\n"


def remove_kernel(kernel_version: str) -> Iterator[str]:
    """
    Remove all DKMS module builds for the given kernel version.
    Called automatically after a kernel is removed.
    Best-effort — failures are warned but not fatal.
    """
    if not is_available():
        return

    mods = modules_for_kernel(kernel_version)
    if not mods:
        yield f"No DKMS modules found for kernel {kernel_version}.\n"
        return

    yield f"Removing DKMS module builds for kernel {kernel_version}...\n"

    from ukm.core.system import privilege_escalation_cmd

    seen: set[tuple[str, str]] = set()

    for mod in mods:
        key = (mod.name, mod.version)
        if key in seen:
            continue
        seen.add(key)

        cmd = privilege_escalation_cmd() + [
            "dkms",
            "remove",
            f"{mod.name}/{mod.version}",
            "-k",
            kernel_version,
            "--all",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            yield f"  Removed {mod.name}/{mod.version} for {kernel_version}.\n"
        else:
            yield f"  ⚠ Could not remove {mod.name}/{mod.version}: {result.stderr.strip()}\n"


def status_summary() -> str:
    """Return a one-line human-readable DKMS status summary."""
    if not is_available():
        return "dkms not installed"
    mods = status()
    if not mods:
        return "no DKMS modules registered"
    broken = [m for m in mods if m.status in ("broken", "uninstalled")]
    installed = [m for m in mods if m.status == "installed"]
    return f"{len(mods)} module(s): {len(installed)} installed" + (
        f", {len(broken)} broken" if broken else ""
    )
