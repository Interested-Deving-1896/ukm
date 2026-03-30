"""Tests for DKMS integration."""

from __future__ import annotations

import unittest.mock as mock
from ukm.core.dkms import (
    is_available, status, modules_for_kernel,
    status_summary,
)

_DKMS_STATUS_OUTPUT = """\
nvidia/550.54.14, 6.8.0-45-generic, x86_64: installed
nvidia/550.54.14, 6.9.0-50-generic, x86_64: installed
virtualbox/7.0.14, 6.8.0-45-generic, x86_64: installed
zfs/2.2.3, 6.8.0-45-generic, x86_64: built
"""

_DKMS_STATUS_BROKEN = """\
nvidia/550.54.14, 6.8.0-45-generic, x86_64: broken
"""


class TestDkmsAvailability:

    @mock.patch("shutil.which", return_value="/usr/sbin/dkms")
    def test_available(self, _):
        assert is_available()

    @mock.patch("shutil.which", return_value=None)
    def test_not_available(self, _):
        assert not is_available()


class TestDkmsStatus:

    @mock.patch("shutil.which", return_value="/usr/sbin/dkms")
    @mock.patch("subprocess.run")
    def test_parses_modules(self, mock_run, _):
        mock_run.return_value = mock.MagicMock(
            returncode=0, stdout=_DKMS_STATUS_OUTPUT
        )
        mods = status()
        assert len(mods) == 4
        names = {m.name for m in mods}
        assert "nvidia" in names
        assert "virtualbox" in names
        assert "zfs" in names

    @mock.patch("shutil.which", return_value="/usr/sbin/dkms")
    @mock.patch("subprocess.run")
    def test_status_fields(self, mock_run, _):
        mock_run.return_value = mock.MagicMock(
            returncode=0, stdout=_DKMS_STATUS_OUTPUT
        )
        mods = status()
        nvidia = next(m for m in mods if m.name == "nvidia" and "6.8.0" in m.kernel)
        assert nvidia.version == "550.54.14"
        assert nvidia.arch == "x86_64"
        assert nvidia.status == "installed"

    @mock.patch("shutil.which", return_value=None)
    def test_returns_empty_when_dkms_missing(self, _):
        assert status() == []

    @mock.patch("shutil.which", return_value="/usr/sbin/dkms")
    @mock.patch("subprocess.run")
    def test_modules_for_kernel(self, mock_run, _):
        mock_run.return_value = mock.MagicMock(
            returncode=0, stdout=_DKMS_STATUS_OUTPUT
        )
        mods = modules_for_kernel("6.8.0-45-generic")
        assert len(mods) == 3
        assert all("6.8.0" in m.kernel for m in mods)

    @mock.patch("shutil.which", return_value="/usr/sbin/dkms")
    @mock.patch("subprocess.run")
    def test_status_summary_with_broken(self, mock_run, _):
        mock_run.return_value = mock.MagicMock(
            returncode=0, stdout=_DKMS_STATUS_BROKEN
        )
        summary = status_summary()
        assert "broken" in summary

    @mock.patch("shutil.which", return_value="/usr/sbin/dkms")
    @mock.patch("subprocess.run")
    def test_status_summary_all_ok(self, mock_run, _):
        mock_run.return_value = mock.MagicMock(
            returncode=0, stdout=_DKMS_STATUS_OUTPUT
        )
        summary = status_summary()
        assert "broken" not in summary
        assert "installed" in summary

    @mock.patch("shutil.which", return_value=None)
    def test_status_summary_no_dkms(self, _):
        assert status_summary() == "dkms not installed"


class TestDkmsAutoinstall:

    @mock.patch("shutil.which", return_value=None)
    def test_skips_when_dkms_missing(self, _):
        from ukm.core.dkms import autoinstall
        lines = list(autoinstall("6.9.0-50-generic"))
        assert any("not found" in l for l in lines)

    @mock.patch("shutil.which", return_value="/usr/sbin/dkms")
    @mock.patch("subprocess.run")
    def test_skips_when_no_modules(self, mock_run, _):
        from ukm.core.dkms import autoinstall
        mock_run.return_value = mock.MagicMock(returncode=0, stdout="")
        lines = list(autoinstall("6.9.0-50-generic"))
        assert any("nothing to rebuild" in l.lower() for l in lines)
