"""Tests for PacmanBackend using subprocess mocking."""

from __future__ import annotations

import unittest.mock as mock
from ukm.core.backends.pacman import PacmanBackend


def make_result(rc=0, stdout="", stderr=""):
    r = mock.MagicMock()
    r.returncode = rc
    r.stdout = stdout
    r.stderr = stderr
    return r


@mock.patch("shutil.which", return_value="/usr/bin/pacman")
class TestPacmanBackend:

    def test_is_available(self, _which):
        assert PacmanBackend().is_available()

    @mock.patch("subprocess.run")
    def test_refresh_cache(self, mock_run, _which):
        mock_run.return_value = make_result(0)
        rc, _, _ = PacmanBackend().refresh_cache()
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "pacman" in cmd
        assert "-Sy" in cmd

    @mock.patch("subprocess.run")
    def test_install(self, mock_run, _which):
        mock_run.return_value = make_result(0)
        rc, _, _ = PacmanBackend().install(["linux-zen"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "-S" in cmd
        assert "linux-zen" in cmd

    @mock.patch("subprocess.run")
    def test_remove(self, mock_run, _which):
        mock_run.return_value = make_result(0)
        rc, _, _ = PacmanBackend().remove(["linux-zen"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "-R" in cmd

    @mock.patch("subprocess.run")
    def test_remove_purge(self, mock_run, _which):
        mock_run.return_value = make_result(0)
        PacmanBackend().remove(["linux-zen"], purge=True)
        cmd = mock_run.call_args[0][0]
        assert "-Rns" in cmd

    @mock.patch("subprocess.run")
    def test_is_installed_true(self, mock_run, _which):
        mock_run.return_value = make_result(0)
        assert PacmanBackend().is_installed("linux-zen")

    @mock.patch("subprocess.run")
    def test_is_installed_false(self, mock_run, _which):
        mock_run.return_value = make_result(1)
        assert not PacmanBackend().is_installed("linux-nonexistent")

    @mock.patch("subprocess.run")
    def test_installed_packages(self, mock_run, _which):
        mock_run.return_value = make_result(0, "linux\nlinux-lts\nlinux-zen\n")
        pkgs = PacmanBackend().installed_packages()
        assert "linux-zen" in pkgs
        assert len(pkgs) == 3
