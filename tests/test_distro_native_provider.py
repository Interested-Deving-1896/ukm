"""Tests for DistroNativeProvider."""

from __future__ import annotations

import unittest.mock as mock

from ukm.core.kernel import KernelFamily, KernelStatus
from ukm.core.providers.distro_native import DistroNativeProvider
from ukm.core.system import PackageManagerKind


def make_backend(pm_kind=PackageManagerKind.APT):
    b = mock.MagicMock()
    b.is_available.return_value = True
    b.installed_packages.return_value = []
    b.is_held.return_value = False
    b.is_installed.return_value = False
    b._run.return_value = (0, "", "")
    return b


class TestDistroNativeProvider:
    def test_family(self):
        p = DistroNativeProvider(make_backend())
        assert p.family == KernelFamily.DISTRO

    def test_supports_all_arches(self):
        p = DistroNativeProvider(make_backend())
        assert p.supports_arch("amd64")
        assert p.supports_arch("arm64")
        assert p.supports_arch("riscv64")

    def test_apt_flavor_extraction(self):
        from ukm.core.providers.distro_native import DistroNativeProvider

        assert DistroNativeProvider._apt_flavor("linux-image-6.8.0-45-generic") == "generic"
        assert DistroNativeProvider._apt_flavor("linux-image-6.8.0-45-lowlatency") == "lowlatency"

    def test_apt_version_extraction(self):
        from ukm.core.providers.distro_native import DistroNativeProvider

        assert DistroNativeProvider._apt_pkg_version("linux-image-6.8.0-45-generic") == "6.8.0"
        assert DistroNativeProvider._apt_pkg_version("linux-image-generic") == ""

    @mock.patch("ukm.core.providers.distro_native.system_info")
    def test_list_apt_returns_entries(self, mock_si):
        mock_si.return_value.package_manager = PackageManagerKind.APT
        mock_si.return_value.running_kernel = "6.8.0-45-generic"

        backend = make_backend()
        backend._run.return_value = (
            0,
            "linux-image-6.8.0-45-generic - Linux kernel image\n"
            "linux-image-6.9.0-50-generic - Linux kernel image\n",
            "",
        )
        backend.installed_packages.return_value = ["linux-image-6.8.0-45-generic"]

        p = DistroNativeProvider(backend)
        entries = p._list_apt("amd64", "6.8.0-45-generic")

        assert len(entries) == 2
        running = [e for e in entries if e.status == KernelStatus.RUNNING]
        assert len(running) == 1
        assert str(running[0].version) == "6.8.0"

    @mock.patch("ukm.core.providers.distro_native.system_info")
    def test_list_pacman_queries_known_kernels(self, mock_si):
        mock_si.return_value.package_manager = PackageManagerKind.PACMAN
        mock_si.return_value.running_kernel = "6.9.0-zen1-1-zen"

        backend = make_backend()

        def run_side_effect(cmd, **kwargs):
            if "pacman" in cmd and "-Si" in cmd:
                pkg = cmd[-1]
                if pkg in ("linux", "linux-zen"):
                    return (0, "Version        : 6.9.0\n", "")
                return (1, "", "not found")
            return (0, "", "")

        backend._run.side_effect = run_side_effect
        backend.is_installed.side_effect = lambda pkg: pkg in ("linux", "linux-zen")

        p = DistroNativeProvider(backend)
        entries = p._list_pacman("amd64", "6.9.0-zen1-1-zen")

        flavors = [e.flavor for e in entries]
        assert "linux" in flavors
        assert "linux-zen" in flavors


class TestDistroNativeFetch:
    """Integration-style tests for the fetch() dispatch."""

    @mock.patch("ukm.core.providers.distro_native.system_info")
    def test_fetch_apt_dispatches(self, mock_si):
        mock_si.return_value.package_manager = PackageManagerKind.APT
        mock_si.return_value.running_kernel = "6.8.0-45-generic"
        b = make_backend()
        b._run.return_value = (0, "linux-image-6.8.0-45-generic - kernel\n", "")
        p = DistroNativeProvider(b)
        entries = p.fetch("amd64")
        assert all(e.family == KernelFamily.DISTRO for e in entries)

    @mock.patch("ukm.core.providers.distro_native.system_info")
    def test_fetch_unknown_pm_returns_empty(self, mock_si):
        from ukm.core.system import PackageManagerKind

        mock_si.return_value.package_manager = PackageManagerKind.UNKNOWN
        mock_si.return_value.running_kernel = ""
        p = DistroNativeProvider(make_backend())
        assert p.fetch("amd64") == []

    @mock.patch("ukm.core.providers.distro_native.system_info")
    def test_fetch_refresh_calls_backend(self, mock_si):
        mock_si.return_value.package_manager = PackageManagerKind.APT
        mock_si.return_value.running_kernel = ""
        b = make_backend()
        DistroNativeProvider(b).fetch("amd64", refresh=True)
        b.refresh_cache.assert_called_once()


class TestDistroNativeInstallRemove:
    @mock.patch("ukm.core.providers.distro_native.system_info")
    def test_install_success(self, mock_si):

        from ukm.core.kernel import KernelEntry, KernelVersion

        mock_si.return_value.package_manager = PackageManagerKind.APT
        mock_si.return_value.running_kernel = ""
        b = make_backend()
        b.install.return_value = (0, "ok\n", "")
        p = DistroNativeProvider(b)
        entry = KernelEntry(
            version=KernelVersion("6.9.0"),
            family=KernelFamily.DISTRO,
            provider_id="distro_native",
            arch="amd64",
            flavor="generic",
            description="linux-image-6.9.0-generic",
        )
        lines = list(p.install(entry))
        b.install.assert_called_once_with(["linux-image-6.9.0-generic"])
        assert any("installed" in line.lower() for line in lines)

    @mock.patch("ukm.core.providers.distro_native.system_info")
    def test_install_failure_raises(self, mock_si):
        import pytest

        from ukm.core.kernel import KernelEntry, KernelVersion

        mock_si.return_value.package_manager = PackageManagerKind.APT
        mock_si.return_value.running_kernel = ""
        b = make_backend()
        b.install.return_value = (1, "", "error\n")
        p = DistroNativeProvider(b)
        entry = KernelEntry(
            version=KernelVersion("6.9.0"),
            family=KernelFamily.DISTRO,
            provider_id="distro_native",
            arch="amd64",
            flavor="generic",
            description="linux-image-6.9.0-generic",
        )
        with pytest.raises(RuntimeError, match="failed"):
            list(p.install(entry))

    @mock.patch("ukm.core.providers.distro_native.system_info")
    def test_remove_success(self, mock_si):
        from ukm.core.kernel import KernelEntry, KernelVersion

        mock_si.return_value.package_manager = PackageManagerKind.APT
        mock_si.return_value.running_kernel = ""
        b = make_backend()
        b.remove.return_value = (0, "removed\n", "")
        p = DistroNativeProvider(b)
        entry = KernelEntry(
            version=KernelVersion("6.8.0"),
            family=KernelFamily.DISTRO,
            provider_id="distro_native",
            arch="amd64",
            flavor="generic",
            description="linux-image-6.8.0-generic",
        )
        lines = list(p.remove(entry))
        b.remove.assert_called_once_with(["linux-image-6.8.0-generic"], purge=False)
        assert any("removed" in line.lower() for line in lines)
