"""Tests for ukm/core/providers/__init__.py (get_providers registry)."""

from __future__ import annotations

import unittest.mock as mock

from ukm.core.providers import get_providers
from ukm.core.providers.mainline_ppa import MainlinePPAProvider
from ukm.core.providers.xanmod import XanModProvider
from ukm.core.providers.liquorix import LiquorixProvider
from ukm.core.providers.distro_native import DistroNativeProvider
from ukm.core.providers.local_file import LocalFileProvider


def _mock_apt_backend():
    b = mock.MagicMock()
    b.name = "apt"
    b._run.return_value = (0, "", "")
    b.installed_packages.return_value = []
    b.is_held.return_value = False
    return b


def _mock_pacman_backend():
    b = mock.MagicMock()
    b.name = "pacman"
    b._run.return_value = (0, "", "")
    b.installed_packages.return_value = []
    b.is_held.return_value = False
    return b


class TestGetProviders:
    def test_returns_list(self):
        with (
            mock.patch("ukm.core.providers.get_backend", return_value=_mock_apt_backend()),
            mock.patch(
                "ukm.core.providers.system_info",
                return_value=mock.MagicMock(
                    arch="amd64",
                    package_manager=mock.MagicMock(value="apt"),
                ),
            ),
        ):
            from ukm.core.system import PackageManagerKind
            with mock.patch(
                "ukm.core.providers.system_info",
                return_value=mock.MagicMock(
                    arch="amd64",
                    package_manager=PackageManagerKind.APT,
                ),
            ):
                providers = get_providers("amd64")
        assert isinstance(providers, list)
        assert len(providers) > 0

    def test_includes_mainline_for_amd64(self):
        with (
            mock.patch("ukm.core.providers.get_backend", return_value=_mock_apt_backend()),
            mock.patch(
                "ukm.core.providers.system_info",
                return_value=mock.MagicMock(
                    arch="amd64",
                    package_manager=mock.MagicMock(value="apt"),
                ),
            ),
        ):
            from ukm.core.system import PackageManagerKind
            with mock.patch(
                "ukm.core.providers.system_info",
                return_value=mock.MagicMock(
                    arch="amd64",
                    package_manager=PackageManagerKind.APT,
                ),
            ):
                providers = get_providers("amd64")
        ids = [p.id for p in providers]
        assert "mainline_ppa" in ids

    def test_excludes_xanmod_for_arm64(self):
        with (
            mock.patch("ukm.core.providers.get_backend", return_value=_mock_apt_backend()),
            mock.patch(
                "ukm.core.providers.system_info",
                return_value=mock.MagicMock(
                    arch="arm64",
                    package_manager=mock.MagicMock(value="apt"),
                ),
            ),
        ):
            from ukm.core.system import PackageManagerKind
            with mock.patch(
                "ukm.core.providers.system_info",
                return_value=mock.MagicMock(
                    arch="arm64",
                    package_manager=PackageManagerKind.APT,
                ),
            ):
                providers = get_providers("arm64")
        ids = [p.id for p in providers]
        assert "xanmod" not in ids

    def test_includes_aur_for_pacman(self):
        with (
            mock.patch("ukm.core.providers.get_backend", return_value=_mock_pacman_backend()),
        ):
            from ukm.core.system import PackageManagerKind
            with mock.patch(
                "ukm.core.providers.system_info",
                return_value=mock.MagicMock(
                    arch="amd64",
                    package_manager=PackageManagerKind.PACMAN,
                ),
            ):
                providers = get_providers("amd64")
        ids = [p.id for p in providers]
        assert "aur" in ids

    def test_excludes_aur_for_apt(self):
        with (
            mock.patch("ukm.core.providers.get_backend", return_value=_mock_apt_backend()),
        ):
            from ukm.core.system import PackageManagerKind
            with mock.patch(
                "ukm.core.providers.system_info",
                return_value=mock.MagicMock(
                    arch="amd64",
                    package_manager=PackageManagerKind.APT,
                ),
            ):
                providers = get_providers("amd64")
        ids = [p.id for p in providers]
        assert "aur" not in ids

    def test_always_includes_local_file(self):
        with (
            mock.patch("ukm.core.providers.get_backend", return_value=_mock_apt_backend()),
        ):
            from ukm.core.system import PackageManagerKind
            with mock.patch(
                "ukm.core.providers.system_info",
                return_value=mock.MagicMock(
                    arch="amd64",
                    package_manager=PackageManagerKind.APT,
                ),
            ):
                providers = get_providers("amd64")
        ids = [p.id for p in providers]
        assert "local_file" in ids


class TestXanModProviderExtra:
    def _make(self):
        b = mock.MagicMock()
        b._run.return_value = (0, "", "")
        b.installed_packages.return_value = []
        b.is_held.return_value = False
        b.refresh_cache.return_value = (0, "", "")
        return XanModProvider(b)

    def test_id(self):
        assert self._make().id == "xanmod"

    def test_family(self):
        from ukm.core.kernel import KernelFamily
        assert self._make().family == KernelFamily.XANMOD

    def test_supported_arches(self):
        assert "amd64" in self._make().supported_arches
        assert "arm64" not in self._make().supported_arches

    @mock.patch("shutil.which", return_value="/usr/bin/apt-get")
    def test_is_available_on_amd64(self, _):
        p = self._make()
        with mock.patch("ukm.core.providers.xanmod.system_info") as si:
            si.return_value.arch = "amd64"
            assert p.is_available()

    @mock.patch("shutil.which", return_value="/usr/bin/apt-get")
    def test_not_available_on_arm64(self, _):
        p = self._make()
        with mock.patch("ukm.core.providers.xanmod.system_info") as si:
            si.return_value.arch = "arm64"
            assert not p.is_available()

    def test_is_repo_configured_true(self):
        b = mock.MagicMock()
        b._run.return_value = (0, "linux-xanmod-edge - XanMod kernel", "")
        p = XanModProvider(b)
        assert p.is_repo_configured()

    def test_is_repo_configured_false(self):
        b = mock.MagicMock()
        b._run.return_value = (0, "", "")
        p = XanModProvider(b)
        assert not p.is_repo_configured()

    def test_flavor_from_pkg(self):
        assert XanModProvider._flavor_from_pkg("linux-xanmod-edge") == "edge"
        assert XanModProvider._flavor_from_pkg("linux-xanmod-lts") == "lts"
        assert XanModProvider._flavor_from_pkg("linux-xanmod-rt-v4") == "rt-v4"
        assert XanModProvider._flavor_from_pkg("linux-xanmod") == "stable"

    def test_fetch_empty_when_no_packages(self):
        b = mock.MagicMock()
        b._run.return_value = (0, "", "")
        b.installed_packages.return_value = []
        b.is_held.return_value = False
        b.refresh_cache.return_value = (0, "", "")
        p = XanModProvider(b)
        with mock.patch("ukm.core.providers.xanmod.system_info") as si:
            si.return_value.running_kernel = ""
            result = p.fetch("amd64")
        assert result == []

    def test_fetch_returns_empty_for_non_amd64(self):
        p = self._make()
        result = p.fetch("arm64")
        assert result == []

    def test_fetch_parses_packages(self):
        apt_output = (
            "linux-xanmod-edge\n"
            "linux-xanmod-lts\n"
            "linux-xanmod-rt\n"
        )
        b = mock.MagicMock()
        b._run.side_effect = [
            (0, apt_output, ""),   # apt-cache search
            (0, "6.9.0-xanmod1", ""),  # version for edge
            (0, "6.9.0-xanmod1", ""),  # version for lts
            (0, "6.9.0-xanmod1", ""),  # version for rt
        ]
        b.installed_packages.return_value = []
        b.is_held.return_value = False

        p = XanModProvider(b)
        with (
            mock.patch("ukm.core.providers.xanmod.system_info") as si,
            mock.patch.object(p, "_version_from_apt", return_value="6.9.0"),
            mock.patch.object(p, "recommended_flavor", return_value="v3"),
        ):
            si.return_value.running_kernel = ""
            result = p.fetch("amd64")
        assert len(result) >= 1

    def test_hold_delegates(self):
        from ukm.core.kernel import KernelEntry, KernelVersion, KernelFamily

        b = mock.MagicMock()
        b.hold.return_value = (0, "held", "")
        p = XanModProvider(b)
        entry = KernelEntry(
            version=KernelVersion("6.9.0"),
            family=KernelFamily.XANMOD,
            provider_id="xanmod",
            arch="amd64",
            flavor="edge",
        )
        rc, _, _ = p.hold(entry)
        assert rc == 0

    def test_unhold_delegates(self):
        from ukm.core.kernel import KernelEntry, KernelVersion, KernelFamily

        b = mock.MagicMock()
        b.unhold.return_value = (0, "unheld", "")
        p = XanModProvider(b)
        entry = KernelEntry(
            version=KernelVersion("6.9.0"),
            family=KernelFamily.XANMOD,
            provider_id="xanmod",
            arch="amd64",
            flavor="edge",
        )
        rc, _, _ = p.unhold(entry)
        assert rc == 0
