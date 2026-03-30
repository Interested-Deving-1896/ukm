"""Tests for GentooProvider."""

from __future__ import annotations

import unittest.mock as mock

import pytest

from ukm.core.backends.portage import PortageBackend
from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion
from ukm.core.providers.gentoo import GentooProvider


def _portage(available=True):
    """Return a MagicMock that passes isinstance(b, PortageBackend)."""
    b = mock.MagicMock(spec=PortageBackend)
    b.is_available.return_value = available
    b._run.return_value = (0, "", "")
    b.installed_packages.return_value = []
    b.is_held.return_value = False
    b.stream.return_value = iter(["compiling...\n", "done.\n"])
    b.hold.return_value = (0, "held\n", "")
    b.unhold.return_value = (0, "unheld\n", "")
    b.list_kernel_sources.return_value = []
    return b


def _entry(ver="6.9.0", flavor="gentoo-kernel"):
    return KernelEntry(
        version=KernelVersion(ver),
        family=KernelFamily.GENTOO,
        provider_id="gentoo",
        arch="amd64",
        flavor=flavor,
    )


class TestGentooIdentity:
    def test_id(self):
        assert GentooProvider(_portage()).id == "gentoo"

    def test_family(self):
        assert GentooProvider(_portage()).family == KernelFamily.GENTOO

    def test_supported_arches(self):
        p = GentooProvider(_portage())
        assert p.supported_arches == ["*"]  # Gentoo supports all arches
        assert "*" in p.supported_arches

    def test_availability_reason_non_empty(self):
        assert GentooProvider(_portage()).availability_reason()

    def test_is_available_delegates(self):
        assert GentooProvider(_portage(available=True)).is_available() is True
        assert GentooProvider(_portage(available=False)).is_available() is False

    def test_requires_portage_backend(self):
        with pytest.raises(TypeError, match="PortageBackend"):
            GentooProvider(mock.MagicMock())  # plain MagicMock, not spec=PortageBackend


class TestGentooFetch:
    def _fetch(self, available_versions=None, installed_versions=None, running="", held=False):
        b = _portage()
        b.is_held.return_value = held
        p = GentooProvider(b)
        with (
            mock.patch.object(p, "_available_versions", return_value=available_versions or []),
            mock.patch.object(p, "_installed_versions", return_value=installed_versions or []),
            mock.patch.object(p, "_running_version", return_value=running),
        ):
            return p.fetch("amd64")

    def test_returns_entries_for_available_versions(self):
        entries = self._fetch(available_versions=["6.9.0", "6.8.0"])
        assert len(entries) > 0
        assert all(e.family == KernelFamily.GENTOO for e in entries)

    def test_empty_when_no_versions(self):
        assert self._fetch() == []

    def test_available_status(self):
        entries = self._fetch(available_versions=["6.9.0"])
        assert any(e.status == KernelStatus.AVAILABLE for e in entries)

    def test_installed_status(self):
        entries = self._fetch(available_versions=["6.9.0"], installed_versions=["6.9.0"])
        assert any(e.status == KernelStatus.INSTALLED for e in entries)

    def test_running_status(self):
        entries = self._fetch(available_versions=["6.9.0"], running="6.9.0")
        assert any(e.status == KernelStatus.RUNNING for e in entries)

    def test_held_status(self):
        entries = self._fetch(available_versions=["6.9.0"], held=True)
        assert any(e.held for e in entries)

    def test_refresh_calls_portage(self):
        b = _portage()
        p = GentooProvider(b)
        with (
            mock.patch.object(p, "_available_versions", return_value=[]),
            mock.patch.object(p, "_installed_versions", return_value=[]),
            mock.patch.object(p, "_running_version", return_value=""),
        ):
            p.fetch("amd64", refresh=True)
        b.refresh_cache.assert_called_once()


class TestGentooInstall:
    def test_streams_emerge_output(self):
        b = _portage()
        b._run.return_value = (0, "sys-kernel/gentoo-kernel-6.9.0\n", "")
        p = GentooProvider(b)
        with mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[]):
            lines = list(p.install(_entry()))
        b.stream.assert_called_once()
        assert any("installed" in line.lower() or "installing" in line.lower() for line in lines)

    def test_raises_when_emerge_fails(self):
        b = _portage()
        b.stream.return_value = iter(["error output\n"])
        b._run.return_value = (1, "", "not found")
        p = GentooProvider(b)
        with (
            mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[]),
            pytest.raises(RuntimeError, match="emerge failed"),
        ):
            list(p.install(_entry()))


class TestGentooRemove:
    def test_remove_calls_portage_remove(self):
        b = _portage()
        b.remove.return_value = (0, "removed\n", "")
        p = GentooProvider(b)
        lines = list(p.remove(_entry()))
        b.remove.assert_called_once()
        assert any("remov" in line.lower() for line in lines)

    def test_remove_source_flavor_skipped(self):
        b = _portage()
        p = GentooProvider(b)
        lines = list(p.remove(_entry(flavor="source")))
        b.remove.assert_not_called()
        assert any("manually" in line.lower() for line in lines)


class TestGentooHoldUnhold:
    def test_hold_delegates_to_portage(self):
        b = _portage()
        rc, _, _ = GentooProvider(b).hold(_entry())
        assert rc == 0
        b.hold.assert_called_once()

    def test_unhold_delegates_to_portage(self):
        b = _portage()
        rc, _, _ = GentooProvider(b).unhold(_entry())
        assert rc == 0
        b.unhold.assert_called_once()


class TestGentooHelpers:
    def test_available_versions_parses_emerge_output(self):
        b = _portage()
        b._run.return_value = (
            0,
            "Latest version available: 6.9.0\nLatest version available: 6.8.0\n",
            "",
        )
        versions = GentooProvider(b)._available_versions("sys-kernel/gentoo-kernel")
        assert "6.9.0" in versions
        assert "6.8.0" in versions

    def test_available_versions_empty_on_failure(self):
        b = _portage()
        b._run.return_value = (1, "", "error")
        assert GentooProvider(b)._available_versions("sys-kernel/gentoo-kernel") == []

    def test_installed_versions_parses_equery_output(self):
        b = _portage()
        b._run.return_value = (0, "6.9.0\n6.8.0\n", "")
        versions = GentooProvider(b)._installed_versions("sys-kernel/gentoo-kernel")
        assert "6.9.0" in versions
        assert "6.8.0" in versions

    def test_installed_versions_empty_on_failure(self):
        b = _portage()
        b._run.return_value = (1, "", "error")
        assert GentooProvider(b)._installed_versions("sys-kernel/gentoo-kernel") == []

    def test_running_version_from_system_info(self):
        b = _portage()
        with mock.patch(
            "ukm.core.system.system_info",
            return_value=mock.MagicMock(running_kernel="6.9.0-gentoo"),
        ):
            ver = GentooProvider(b)._running_version()
        assert "6.9.0" in ver

    def test_version_from_src_path(self):
        p = GentooProvider(_portage())
        # The regex captures everything after "linux-" up to whitespace/slash
        assert p._version_from_src_path("/usr/src/linux-6.9.0-gentoo").startswith("6.9.0")
        assert p._version_from_src_path("/usr/src/linux-6.8.12-gentoo-r1").startswith("6.8.12")
        assert p._version_from_src_path("/usr/src/linux") == ""
