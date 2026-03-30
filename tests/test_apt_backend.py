"""Tests for AptBackend using subprocess mocking."""

from __future__ import annotations

import unittest.mock as mock
from ukm.core.backends.apt import AptBackend


def make_result(rc=0, stdout="", stderr=""):
    r = mock.MagicMock()
    r.returncode = rc
    r.stdout = stdout
    r.stderr = stderr
    return r


@mock.patch("shutil.which", return_value="/usr/bin/apt-get")
class TestAptBackend:
    def test_is_available(self, _which):
        assert AptBackend().is_available()

    @mock.patch("subprocess.run")
    def test_refresh_cache(self, mock_run, _which):
        mock_run.return_value = make_result(0, "", "")
        rc, out, err = AptBackend().refresh_cache()
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "apt-get" in cmd
        assert "update" in cmd

    @mock.patch("subprocess.run")
    def test_install(self, mock_run, _which):
        mock_run.return_value = make_result(0, "Setting up linux-image...\n", "")
        rc, out, err = AptBackend().install(["linux-image-6.9.0-generic"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "install" in cmd
        assert "linux-image-6.9.0-generic" in cmd

    @mock.patch("subprocess.run")
    def test_install_failure(self, mock_run, _which):
        mock_run.return_value = make_result(1, "", "E: Unable to locate package")
        rc, out, err = AptBackend().install(["linux-image-nonexistent"])
        assert rc == 1
        assert "Unable to locate" in err

    @mock.patch("subprocess.run")
    def test_remove(self, mock_run, _which):
        mock_run.return_value = make_result(0, "Removing linux-image...\n", "")
        rc, out, err = AptBackend().remove(["linux-image-6.9.0-generic"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "remove" in cmd

    @mock.patch("subprocess.run")
    def test_purge(self, mock_run, _which):
        mock_run.return_value = make_result(0, "", "")
        AptBackend().remove(["linux-image-6.9.0-generic"], purge=True)
        cmd = mock_run.call_args[0][0]
        assert "purge" in cmd

    @mock.patch("subprocess.run")
    def test_hold(self, mock_run, _which):
        mock_run.return_value = make_result(0, "", "")
        rc, _, _ = AptBackend().hold(["linux-image-6.9.0-generic"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "apt-mark" in cmd
        assert "hold" in cmd

    @mock.patch("subprocess.run")
    def test_unhold(self, mock_run, _which):
        mock_run.return_value = make_result(0, "", "")
        rc, _, _ = AptBackend().unhold(["linux-image-6.9.0-generic"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "unhold" in cmd

    @mock.patch("subprocess.run")
    def test_is_installed_true(self, mock_run, _which):
        mock_run.return_value = make_result(0, "install ok installed", "")
        assert AptBackend().is_installed("linux-image-6.9.0-generic")

    @mock.patch("subprocess.run")
    def test_is_installed_false(self, mock_run, _which):
        mock_run.return_value = make_result(1, "", "")
        assert not AptBackend().is_installed("linux-image-nonexistent")

    @mock.patch("subprocess.run")
    def test_is_held_true(self, mock_run, _which):
        mock_run.return_value = make_result(0, "linux-image-6.9.0-generic\n", "")
        assert AptBackend().is_held("linux-image-6.9.0-generic")

    @mock.patch("subprocess.run")
    def test_is_held_false(self, mock_run, _which):
        mock_run.return_value = make_result(0, "linux-image-6.8.0-generic\n", "")
        assert not AptBackend().is_held("linux-image-6.9.0-generic")

    @mock.patch("subprocess.run")
    def test_installed_packages(self, mock_run, _which):
        mock_run.return_value = make_result(
            0, "linux-image-6.9.0-generic\nlinux-image-6.8.0-generic\n", ""
        )
        pkgs = AptBackend().installed_packages("linux-image")
        assert "linux-image-6.9.0-generic" in pkgs
        assert len(pkgs) == 2
