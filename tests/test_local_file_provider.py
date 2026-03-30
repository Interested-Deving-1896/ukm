"""Tests for LocalFileProvider."""

from __future__ import annotations

import unittest.mock as mock

import pytest

from ukm.core.kernel import KernelFamily, KernelStatus
from ukm.core.providers.local_file import LocalFileProvider


def make_backend(available=True, install_rc=0, remove_rc=0, installed=None):
    b = mock.MagicMock()
    b.is_available.return_value = available
    b.install_local.return_value = (install_rc, "ok\n", "")
    b.remove.return_value = (remove_rc, "removed\n", "")
    b.installed_packages.return_value = installed or []
    return b


class TestLocalFileProviderIdentity:
    def test_id(self):
        assert LocalFileProvider(make_backend()).id == "local_file"

    def test_family(self):
        assert LocalFileProvider(make_backend()).family == KernelFamily.LOCAL

    def test_supports_all_arches(self):
        p = LocalFileProvider(make_backend())
        assert p.supports_arch("amd64")
        assert p.supports_arch("arm64")
        assert p.supports_arch("riscv64")

    def test_fetch_returns_empty(self):
        assert LocalFileProvider(make_backend()).fetch("amd64") == []

    def test_is_available_delegates_to_backend(self):
        assert LocalFileProvider(make_backend(available=True)).is_available() is True
        assert LocalFileProvider(make_backend(available=False)).is_available() is False


class TestVersionFromFilename:
    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("linux-image-6.9.0-generic_6.9.0-1_amd64.deb", "6.9.0"),
            ("linux-image-6.9.0-061900-generic_6.9.0-061900.202405010000_amd64.deb", "6.9.0"),
            ("linux-6.8.12-arch1-1-x86_64.pkg.tar.zst", "6.8.12"),
            ("kernel-6.10.0-0.rc3.20240601.fc41.x86_64.rpm", "6.10.0"),
            ("linux-image-6.9.0-rc3_amd64.deb", "6.9.0-rc3"),
            ("no-version-here.deb", ""),
        ],
    )
    def test_version_extraction(self, filename, expected):
        result = LocalFileProvider._version_from_filename(filename)
        assert result == expected


class TestFlavorFromFilename:
    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("linux-image-6.9.0-generic_amd64.deb", "generic"),
            ("linux-image-6.9.0-lowlatency_amd64.deb", "lowlatency"),
            ("linux-image-6.9.0-rt_amd64.deb", "rt"),
            ("linux-zen-6.9.0.pkg.tar.zst", "zen"),
            ("linux-hardened-6.9.0.pkg.tar.zst", "hardened"),
            ("linux-lts-6.6.0.pkg.tar.zst", "lts"),
            ("linux-custom-6.9.0.deb", "custom"),
        ],
    )
    def test_flavor_detection(self, filename, expected):
        result = LocalFileProvider._flavor_from_filename(filename)
        assert result == expected


class TestEntryFromPath:
    def test_creates_entry_with_correct_fields(self):
        p = LocalFileProvider(make_backend())
        entry = p.entry_from_path("/tmp/linux-image-6.9.0-generic_6.9.0-1_amd64.deb", "amd64")
        assert str(entry.version) == "6.9.0"
        assert entry.family == KernelFamily.LOCAL
        assert entry.provider_id == "local_file"
        assert entry.arch == "amd64"
        assert entry.flavor == "generic"
        assert entry.status == KernelStatus.AVAILABLE
        assert entry.source_url == "/tmp/linux-image-6.9.0-generic_6.9.0-1_amd64.deb"

    def test_unknown_version_falls_back(self):
        p = LocalFileProvider(make_backend())
        entry = p.entry_from_path("/tmp/mykernel.deb", "amd64")
        assert str(entry.version) == "unknown"
        assert entry.flavor == "custom"


class TestInstall:
    def test_install_success(self, tmp_path):
        pkg = tmp_path / "linux-image-6.9.0-generic_amd64.deb"
        pkg.write_bytes(b"fake deb")
        b = make_backend(install_rc=0)
        p = LocalFileProvider(b)
        entry = p.entry_from_path(str(pkg), "amd64")
        lines = list(p.install(entry))
        b.install_local.assert_called_once_with([str(pkg)])
        assert any("installed" in line.lower() for line in lines)

    def test_install_missing_file_raises(self):
        p = LocalFileProvider(make_backend())
        entry = p.entry_from_path("/nonexistent/kernel.deb", "amd64")
        with pytest.raises(RuntimeError, match="not found"):
            list(p.install(entry))

    def test_install_backend_failure_raises(self, tmp_path):
        pkg = tmp_path / "linux-image-6.9.0-generic_amd64.deb"
        pkg.write_bytes(b"fake deb")
        b = make_backend(install_rc=1)
        b.install_local.return_value = (1, "", "dpkg error\n")
        p = LocalFileProvider(b)
        entry = p.entry_from_path(str(pkg), "amd64")
        with pytest.raises(RuntimeError, match="failed"):
            list(p.install(entry))


class TestRemove:
    def test_remove_matching_packages(self):
        b = make_backend(remove_rc=0, installed=["linux-image-6.9.0-generic"])
        p = LocalFileProvider(b)
        entry = p.entry_from_path("/tmp/linux-image-6.9.0-generic_amd64.deb", "amd64")
        lines = list(p.remove(entry))
        b.remove.assert_called_once_with(["linux-image-6.9.0-generic"], purge=False)
        assert any("removed" in line.lower() for line in lines)

    def test_remove_no_matching_packages(self):
        b = make_backend(installed=[])
        p = LocalFileProvider(b)
        entry = p.entry_from_path("/tmp/linux-image-6.9.0-generic_amd64.deb", "amd64")
        lines = list(p.remove(entry))
        b.remove.assert_not_called()
        assert any("no matching" in line.lower() for line in lines)

    def test_remove_failure_raises(self):
        b = make_backend(remove_rc=1, installed=["linux-image-6.9.0-generic"])
        b.remove.return_value = (1, "", "error\n")
        p = LocalFileProvider(b)
        entry = p.entry_from_path("/tmp/linux-image-6.9.0-generic_amd64.deb", "amd64")
        with pytest.raises(RuntimeError, match="failed"):
            list(p.remove(entry))
