"""Tests for LiquorixProvider."""

from __future__ import annotations

import unittest.mock as mock

import pytest

from ukm.core.kernel import KernelFamily, KernelStatus
from ukm.core.providers.liquorix import LiquorixProvider


def _backend(available=True, run_out="", run_rc=0, installed=None):
    b = mock.MagicMock()
    b.is_available.return_value = available
    b._run.return_value = (run_rc, run_out, "")
    b.installed_packages.return_value = installed or []
    b.is_held.return_value = False
    return b


class TestLiquorixIdentity:
    def test_id(self):
        assert LiquorixProvider(_backend()).id == "liquorix"

    def test_family(self):
        assert LiquorixProvider(_backend()).family == KernelFamily.LIQUORIX

    def test_supported_arches(self):
        p = LiquorixProvider(_backend())
        assert "amd64" in p.supported_arches
        assert "arm64" not in p.supported_arches

    def test_availability_reason_non_empty(self):
        assert LiquorixProvider(_backend()).availability_reason()

    def test_is_available_false_on_non_amd64(self):
        with mock.patch(
            "ukm.core.providers.liquorix.system_info",
            return_value=mock.MagicMock(arch="arm64"),
        ):
            assert LiquorixProvider(_backend()).is_available() is False

    def test_is_available_false_when_no_apt(self):
        with (
            mock.patch(
                "ukm.core.providers.liquorix.system_info",
                return_value=mock.MagicMock(arch="amd64"),
            ),
            mock.patch("shutil.which", return_value=None),
        ):
            assert LiquorixProvider(_backend()).is_available() is False

    def test_fetch_empty_on_non_amd64(self):
        assert LiquorixProvider(_backend()).fetch("arm64") == []

    def test_fetch_empty_on_apt_failure(self):
        b = _backend(run_rc=1)
        with mock.patch(
            "ukm.core.providers.liquorix.system_info",
            return_value=mock.MagicMock(running_kernel="6.8.0"),
        ):
            assert LiquorixProvider(b).fetch("amd64") == []


class TestLiquorixFetch:
    # apt-cache search --names-only output: "pkg_name - description"
    _APT_OUT = (
        "linux-image-liquorix-amd64 - Liquorix kernel image\n"
        "linux-headers-liquorix-amd64 - Liquorix kernel headers\n"
    )
    _VER = "6.9.0"

    def _fetch(self, out=_APT_OUT, installed=None, running="6.8.0", ver=_VER):
        b = _backend(run_out=out, installed=installed or [])
        with (
            mock.patch(
                "ukm.core.providers.liquorix.system_info",
                return_value=mock.MagicMock(running_kernel=running),
            ),
            mock.patch.object(LiquorixProvider, "_version_from_apt", return_value=ver),
        ):
            return LiquorixProvider(b).fetch("amd64")

    def test_returns_entries(self):
        entries = self._fetch()
        assert len(entries) > 0
        assert all(e.family == KernelFamily.LIQUORIX for e in entries)

    def test_installed_status(self):
        entries = self._fetch(installed=["linux-image-liquorix-amd64"])
        assert any(e.status == KernelStatus.INSTALLED for e in entries)

    def test_running_status(self):
        entries = self._fetch(running="6.9.0-1-liquorix-amd64")
        assert any(e.status == KernelStatus.RUNNING for e in entries)

    def test_held_status(self):
        b = _backend(run_out=self._APT_OUT, installed=["linux-image-liquorix-amd64"])
        b.is_held.return_value = True
        with (
            mock.patch(
                "ukm.core.providers.liquorix.system_info",
                return_value=mock.MagicMock(running_kernel="6.8.0"),
            ),
            mock.patch.object(LiquorixProvider, "_version_from_apt", return_value=self._VER),
        ):
            entries = LiquorixProvider(b).fetch("amd64")
        assert any(e.held for e in entries)

    def test_empty_on_no_packages(self):
        assert self._fetch(out="") == []

    def test_empty_when_version_not_found(self):
        # _version_from_apt returns "" → entry skipped
        entries = self._fetch(ver="")
        assert entries == []


class TestLiquorixInstall:
    def _entry(self, ver="6.9.0"):
        from ukm.core.kernel import KernelEntry, KernelVersion

        return KernelEntry(
            version=KernelVersion(ver),
            family=KernelFamily.LIQUORIX,
            provider_id="liquorix",
            arch="amd64",
            flavor="liquorix",
        )

    def test_install_streams_apt_output(self):
        b = _backend()
        b.stream.return_value = iter(["Reading package lists...\n", "Done.\n"])
        p = LiquorixProvider(b)
        with mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[]):
            lines = list(p.install(self._entry()))
        b.stream.assert_called_once()
        assert any("installed" in line.lower() or "installing" in line.lower() for line in lines)

    def test_install_raises_on_error_in_output(self):
        b = _backend()
        b.stream.return_value = iter(["E: Unable to locate package\n"])
        p = LiquorixProvider(b)
        with (
            mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[]),
            pytest.raises(RuntimeError, match="failed"),
        ):
            list(p.install(self._entry()))


class TestLiquorixRemove:
    def _entry(self, ver="6.9.0"):
        from ukm.core.kernel import KernelEntry, KernelVersion

        return KernelEntry(
            version=KernelVersion(ver),
            family=KernelFamily.LIQUORIX,
            provider_id="liquorix",
            arch="amd64",
            flavor="liquorix",
        )

    def test_remove_matching_packages(self):
        b = _backend()
        # installed_packages("linux-") returns packages containing the version
        b.installed_packages.return_value = [
            "linux-image-liquorix-amd64-6.9.0",
            "linux-headers-liquorix-amd64-6.9.0",
        ]
        b.remove.return_value = (0, "removed\n", "")
        lines = list(LiquorixProvider(b).remove(self._entry()))
        b.remove.assert_called_once()
        assert any("removed" in line.lower() for line in lines)

    def test_remove_no_matching_packages(self):
        b = _backend()
        b.installed_packages.return_value = []
        lines = list(LiquorixProvider(b).remove(self._entry()))
        b.remove.assert_not_called()
        assert any("no matching" in line.lower() for line in lines)

    def test_remove_failure_raises(self):
        b = _backend()
        b.installed_packages.return_value = ["linux-image-liquorix-amd64-6.9.0"]
        b.remove.return_value = (1, "", "error\n")
        with pytest.raises(RuntimeError, match="failed"):
            list(LiquorixProvider(b).remove(self._entry()))
