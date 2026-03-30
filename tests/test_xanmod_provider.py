"""Tests for XanModProvider."""

from __future__ import annotations

import unittest.mock as mock

from ukm.core.kernel import KernelFamily, KernelStatus
from ukm.core.providers.xanmod import XanModProvider


def _backend(apt_search_out="", installed=None, held=False, rc=0):
    b = mock.MagicMock()
    b._run.return_value = (rc, apt_search_out, "")
    b.installed_packages.return_value = installed or []
    b.is_held.return_value = held
    b.refresh_cache.return_value = None
    b.install.return_value = (0, "ok\n", "")
    b.remove.return_value = (0, "ok\n", "")
    return b


_APT_SEARCH_OUT = """\
linux-xanmod-edge - XanMod kernel edge
linux-xanmod-lts - XanMod kernel LTS
linux-xanmod-rt - XanMod kernel RT
linux-xanmod-edge-v3 - XanMod kernel edge v3
"""


class TestXanModProviderIdentity:
    def test_id(self):
        assert XanModProvider(_backend()).id == "xanmod"

    def test_family(self):
        assert XanModProvider(_backend()).family == KernelFamily.XANMOD

    def test_supported_arches(self):
        p = XanModProvider(_backend())
        assert "amd64" in p.supported_arches
        assert "arm64" not in p.supported_arches

    def test_availability_reason_non_empty(self):
        assert XanModProvider(_backend()).availability_reason()

    def test_is_available_false_on_non_amd64(self):
        with mock.patch(
            "ukm.core.providers.xanmod.system_info",
            return_value=mock.MagicMock(arch="arm64"),
        ):
            assert XanModProvider(_backend()).is_available() is False

    def test_fetch_empty_on_non_amd64(self):
        assert XanModProvider(_backend()).fetch("arm64") == []

    def test_fetch_empty_on_apt_failure(self):
        b = _backend(rc=1)
        with mock.patch(
            "ukm.core.providers.xanmod.system_info",
            return_value=mock.MagicMock(running_kernel="6.8.0"),
        ):
            assert XanModProvider(b).fetch("amd64") == []


class TestXanModFetch:
    def _fetch(self, apt_out, installed=None, running="6.8.0", recommended="v3"):
        b = _backend(apt_search_out=apt_out, installed=installed or [])
        with (
            mock.patch(
                "ukm.core.providers.xanmod.system_info",
                return_value=mock.MagicMock(running_kernel=running),
            ),
            mock.patch(
                "ukm.core.providers.xanmod.XanModProvider.recommended_flavor",
                return_value=recommended,
            ),
            mock.patch(
                "ukm.core.providers.xanmod.XanModProvider._version_from_apt",
                return_value="6.9.0",
            ),
        ):
            return XanModProvider(b).fetch("amd64")

    def test_returns_entries_for_each_package(self):
        entries = self._fetch(_APT_SEARCH_OUT)
        assert len(entries) > 0
        assert all(e.family == KernelFamily.XANMOD for e in entries)

    def test_installed_status(self):
        b = _backend(apt_search_out="linux-xanmod-edge - XanMod\n", installed=["linux-xanmod-edge"])
        with (
            mock.patch(
                "ukm.core.providers.xanmod.system_info",
                return_value=mock.MagicMock(running_kernel="6.8.0"),
            ),
            mock.patch(
                "ukm.core.providers.xanmod.XanModProvider.recommended_flavor",
                return_value="v3",
            ),
            mock.patch(
                "ukm.core.providers.xanmod.XanModProvider._version_from_apt",
                return_value="6.9.0",
            ),
        ):
            entries = XanModProvider(b).fetch("amd64")
        assert any(e.status == KernelStatus.INSTALLED for e in entries)

    def test_refresh_calls_backend(self):
        b = _backend()
        with (
            mock.patch(
                "ukm.core.providers.xanmod.system_info",
                return_value=mock.MagicMock(running_kernel="6.8.0"),
            ),
            mock.patch(
                "ukm.core.providers.xanmod.XanModProvider.recommended_flavor",
                return_value="v3",
            ),
        ):
            XanModProvider(b).fetch("amd64", refresh=True)
        b.refresh_cache.assert_called_once()


class TestXanModFlavorParsing:
    @mock.patch("ukm.core.providers.xanmod.XanModProvider._version_from_apt", return_value="")
    def test_flavor_from_pkg(self, _):
        p = XanModProvider(_backend())
        assert p._flavor_from_pkg("linux-xanmod-edge") == "edge"
        assert p._flavor_from_pkg("linux-xanmod-lts") == "lts"
        assert p._flavor_from_pkg("linux-xanmod-rt") == "rt"
        assert p._flavor_from_pkg("linux-xanmod-edge-v3") == "edge"  # edge matched before edge-v3
        assert p._flavor_from_pkg("linux-xanmod") == "stable"  # fallback when no suffix
