"""
Ubuntu Mainline PPA provider.

Fetches the kernel index from https://kernel.ubuntu.com/mainline/,
downloads .deb packages, verifies SHA256 checksums, and installs via dpkg.

This is the core of bkw777/mainline, re-implemented as a provider.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import urllib.request
from pathlib import Path
from typing import Iterator

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion
from ukm.core.providers.base import KernelProvider
from ukm.core.system import system_info

# The PPA index root
_PPA_BASE = "https://kernel.ubuntu.com/mainline/"

# Local cache directory
_CACHE_DIR = Path.home() / ".cache" / "ukm" / "mainline_ppa"

# Architectures the PPA publishes
_PPA_ARCHES = ["amd64", "arm64", "armhf", "ppc64el", "s390x", "i386"]


class MainlinePPAProvider(KernelProvider):

    @property
    def id(self) -> str:
        return "mainline_ppa"

    @property
    def display_name(self) -> str:
        return "Ubuntu Mainline PPA"

    @property
    def family(self) -> KernelFamily:
        return KernelFamily.MAINLINE

    @property
    def supported_arches(self) -> list[str]:
        return _PPA_ARCHES

    def is_available(self) -> bool:
        # Requires dpkg (Debian-family) and network access
        import shutil
        return bool(shutil.which("dpkg"))

    def availability_reason(self) -> str:
        return (
            "Ubuntu Mainline PPA kernels are distributed as .deb packages and "
            "require dpkg to install. This provider is only available on "
            "Debian/Ubuntu-based systems."
        )

    # ------------------------------------------------------------------
    # list()
    # ------------------------------------------------------------------

    def list(self, arch: str, refresh: bool = False) -> list[KernelEntry]:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        index_cache = _CACHE_DIR / "index.json"

        if refresh or not index_cache.exists():
            entries = self._fetch_index(arch)
            index_cache.write_text(json.dumps(
                [self._entry_to_dict(e) for e in entries], indent=2
            ))
        else:
            raw = json.loads(index_cache.read_text())
            entries = [self._dict_to_entry(d, arch) for d in raw]

        # Overlay installed/running status
        installed = self._get_installed_versions()
        running = system_info().running_kernel

        for entry in entries:
            ver_str = str(entry.version)
            if any(ver_str in pkg for pkg in installed):
                entry.status = KernelStatus.INSTALLED
            if running and ver_str in running:
                entry.status = KernelStatus.RUNNING
            if self._backend.is_held(f"linux-image-{ver_str}-generic"):
                entry.held = True
                entry.status = KernelStatus.HELD

        return sorted(entries, key=lambda e: e.version, reverse=True)

    # ------------------------------------------------------------------
    # install()
    # ------------------------------------------------------------------

    def install(self, entry: KernelEntry) -> Iterator[str]:
        arch = system_info().arch
        ver = str(entry.version)
        ppa_url = f"{_PPA_BASE}{ver}/"

        yield f"Fetching package list for {ver}...\n"
        try:
            pkg_urls, checksums = self._fetch_package_urls(ppa_url, arch)
        except Exception as e:
            raise RuntimeError(f"Failed to fetch package list: {e}") from e

        with tempfile.TemporaryDirectory(prefix="ukm-mainline-") as tmpdir:
            tmp = Path(tmpdir)
            debs: list[Path] = []

            for url in pkg_urls:
                fname = url.split("/")[-1]
                dest = tmp / fname
                yield f"Downloading {fname}...\n"
                try:
                    urllib.request.urlretrieve(url, dest)
                except Exception as e:
                    raise RuntimeError(f"Download failed for {fname}: {e}") from e

                # Verify checksum
                expected = checksums.get(fname)
                if expected:
                    actual = hashlib.sha256(dest.read_bytes()).hexdigest()
                    if actual != expected:
                        raise RuntimeError(
                            f"SHA256 mismatch for {fname}:\n"
                            f"  expected: {expected}\n"
                            f"  got:      {actual}"
                        )
                    yield f"  ✓ checksum OK\n"
                debs.append(dest)

            yield "Installing packages...\n"
            from ukm.core.system import privilege_escalation_cmd
            install_cmd = privilege_escalation_cmd() + ["dpkg", "-i"] + [str(d) for d in debs]
            rc = 0
            for line in self._backend.stream(install_cmd):
                yield line
                if line.startswith("dpkg: error") or "Error" in line:
                    rc = 1
            # Confirm via dpkg exit code by re-querying status
            check_rc, _, _ = self._backend._run(
                ["dpkg-query", "-W", "-f=${Status}", f"linux-image-{ver}-generic"]
            )
            if check_rc != 0 and rc != 0:
                raise RuntimeError(f"dpkg install failed for kernel {ver}")
            yield f"Kernel {ver} installed successfully.\n"

    # ------------------------------------------------------------------
    # remove()
    # ------------------------------------------------------------------

    def remove(self, entry: KernelEntry, purge: bool = False) -> Iterator[str]:
        ver = str(entry.version)
        yield f"Removing kernel {ver}...\n"

        # Find all installed packages for this version
        pkgs = [
            p for p in self._backend.installed_packages("linux-")
            if ver.replace(".", ".") in p or ver in p
        ]
        if not pkgs:
            yield f"No installed packages found for {ver}.\n"
            return

        rc, out, err = self._backend.remove(pkgs, purge=purge)
        if out:
            yield out
        if err:
            yield err
        if rc != 0:
            raise RuntimeError(f"Removal failed (exit {rc})")
        yield f"Kernel {ver} removed.\n"

    # ------------------------------------------------------------------
    # hold / unhold
    # ------------------------------------------------------------------

    def hold(self, entry: KernelEntry) -> tuple[int, str, str]:
        ver = str(entry.version)
        pkgs = [
            p for p in self._backend.installed_packages("linux-")
            if ver in p
        ]
        return self._backend.hold(pkgs) if pkgs else (0, "Nothing to hold.", "")

    def unhold(self, entry: KernelEntry) -> tuple[int, str, str]:
        ver = str(entry.version)
        pkgs = [
            p for p in self._backend.installed_packages("linux-")
            if ver in p
        ]
        return self._backend.unhold(pkgs) if pkgs else (0, "Nothing to unhold.", "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_index(self, arch: str) -> list[KernelEntry]:
        """Scrape the PPA index page for all available kernel versions."""
        with urllib.request.urlopen(_PPA_BASE, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Each kernel version is a link like: <a href="v6.9/">v6.9/</a>
        versions = re.findall(r'href="(v[\d.]+(?:-rc\d+)?)/?"', html)
        entries = []
        for v in versions:
            ver_str = v.lstrip("v")
            entries.append(KernelEntry(
                version=KernelVersion(ver_str),
                family=self.family,
                provider_id=self.id,
                arch=arch,
                flavor="generic",
                source_url=f"{_PPA_BASE}{v}/",
            ))
        return entries

    def _fetch_package_urls(
        self, ppa_url: str, arch: str
    ) -> tuple[list[str], dict[str, str]]:
        """
        Fetch the per-version index page and extract .deb URLs + checksums.
        Returns (urls, {filename: sha256}).
        """
        with urllib.request.urlopen(ppa_url, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Find CHECKSUMS file
        checksums: dict[str, str] = {}
        checksum_match = re.search(r'href="(CHECKSUMS[^"]*)"', html)
        if checksum_match:
            cs_url = ppa_url + checksum_match.group(1)
            try:
                with urllib.request.urlopen(cs_url, timeout=10) as r:
                    for line in r.read().decode().splitlines():
                        parts = line.split()
                        if len(parts) == 2:
                            checksums[parts[1].lstrip("./")] = parts[0]
            except Exception:
                pass

        # Find .deb files for this arch
        deb_pattern = re.compile(
            rf'href="(linux-(?:image|headers|modules)[^"]*_{arch}\.deb)"'
        )
        filenames = deb_pattern.findall(html)
        urls = [ppa_url + f for f in filenames]
        return urls, checksums

    def _get_installed_versions(self) -> list[str]:
        return self._backend.installed_packages("linux-image-")

    @staticmethod
    def _entry_to_dict(e: KernelEntry) -> dict:
        return {
            "version": str(e.version),
            "arch": e.arch,
            "flavor": e.flavor,
            "source_url": e.source_url,
        }

    @staticmethod
    def _dict_to_entry(d: dict, arch: str) -> KernelEntry:
        return KernelEntry(
            version=KernelVersion(d["version"]),
            family=KernelFamily.MAINLINE,
            provider_id="mainline_ppa",
            arch=d.get("arch", arch),
            flavor=d.get("flavor", "generic"),
            source_url=d.get("source_url"),
        )
