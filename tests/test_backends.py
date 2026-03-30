"""Tests for package manager backends (apt, dnf, zypper, apk, pacman)."""

from __future__ import annotations

import unittest.mock as mock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_ok(stdout="", stderr=""):
    return mock.MagicMock(returncode=0, stdout=stdout, stderr=stderr)


def _run_fail(stdout="", stderr="error"):
    return mock.MagicMock(returncode=1, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# AptBackend
# ---------------------------------------------------------------------------


class TestAptBackend:
    def _make(self):
        from ukm.core.backends.apt import AptBackend

        return AptBackend()

    @mock.patch("shutil.which", return_value="/usr/bin/apt-get")
    def test_is_available(self, _):
        assert self._make().is_available()

    @mock.patch("shutil.which", return_value=None)
    def test_not_available(self, _):
        assert not self._make().is_available()

    @mock.patch("subprocess.run", return_value=_run_ok("ok"))
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install(self, _, mock_run):
        rc, out, err = self._make().install(["linux-image-6.9.0"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "apt-get" in cmd
        assert "install" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok("ok"))
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install_local(self, _, mock_run):
        rc, _, _ = self._make().install_local(["/tmp/kernel.deb"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "dpkg" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_remove(self, _, mock_run):
        rc, _, _ = self._make().remove(["linux-image-6.8.0"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "remove" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_remove_purge(self, _, mock_run):
        self._make().remove(["linux-image-6.8.0"], purge=True)
        cmd = mock_run.call_args[0][0]
        assert "purge" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_hold(self, _, mock_run):
        rc, _, _ = self._make().hold(["linux-image-6.9.0"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "apt-mark" in cmd
        assert "hold" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_unhold(self, _, mock_run):
        rc, _, _ = self._make().unhold(["linux-image-6.9.0"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "unhold" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok("install ok installed"))
    def test_is_installed_true(self, _):
        assert self._make().is_installed("linux-image-6.9.0")

    @mock.patch("subprocess.run", return_value=_run_ok("deinstall ok not-installed"))
    def test_is_installed_false(self, _):
        assert not self._make().is_installed("linux-image-6.9.0")

    @mock.patch("subprocess.run", return_value=_run_ok("linux-image-6.9.0\n"))
    def test_is_held_true(self, _):
        assert self._make().is_held("linux-image-6.9.0")

    @mock.patch("subprocess.run", return_value=_run_ok(""))
    def test_is_held_false(self, _):
        assert not self._make().is_held("linux-image-6.9.0")

    @mock.patch("subprocess.run", return_value=_run_ok("linux-image-6.9.0\nlinux-image-6.8.0\n"))
    def test_installed_packages(self, _):
        pkgs = self._make().installed_packages()
        assert "linux-image-6.9.0" in pkgs

    @mock.patch("subprocess.run", return_value=_run_fail())
    def test_installed_packages_failure(self, _):
        assert self._make().installed_packages() == []

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_refresh_cache(self, _, mock_run):
        rc, _, _ = self._make().refresh_cache()
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "apt-get" in cmd
        assert "update" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_add_repository_no_key(self, _, mock_run):
        """add_repository without a key URL just writes the sources file."""
        rc, _, _ = self._make().add_repository("deb http://example.com/repo releases main")
        assert rc == 0
        # Should call tee to write the sources file
        cmd = mock_run.call_args[0][0]
        assert "tee" in cmd

    @mock.patch("subprocess.run")
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_add_repository_with_key_curl_fails(self, _, mock_run):
        """If curl fails, add_repository returns the error immediately."""
        mock_run.return_value = _run_fail(stderr="curl: not found")
        rc, _, err = self._make().add_repository(
            "deb http://example.com/repo releases main",
            key_url="https://example.com/key.asc",
        )
        assert rc != 0

    @mock.patch("subprocess.run")
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    @mock.patch("os.unlink")
    def test_add_repository_with_key_success(self, mock_unlink, _, mock_run):
        """Full add_repository flow: curl → gpg --dearmor → tee."""
        mock_run.side_effect = [
            _run_ok("-----BEGIN PGP PUBLIC KEY BLOCK-----\n"),  # curl
            _run_ok(),   # gpg --dearmor
            _run_ok(),   # tee sources file
        ]
        rc, _, _ = self._make().add_repository(
            "deb http://example.com/repo releases main",
            key_url="https://example.com/key.asc",
        )
        assert rc == 0
        mock_unlink.assert_called_once()  # temp key file cleaned up

    @mock.patch("subprocess.run")
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    @mock.patch("os.unlink")
    def test_add_repository_gpg_fails(self, mock_unlink, _, mock_run):
        """If gpg --dearmor fails, propagate the error."""
        mock_run.side_effect = [
            _run_ok("key data"),  # curl succeeds
            _run_fail(stderr="gpg error"),  # gpg fails
        ]
        rc, _, _ = self._make().add_repository(
            "deb http://example.com/repo releases main",
            key_url="https://example.com/key.asc",
        )
        assert rc != 0
        mock_unlink.assert_called_once()


# ---------------------------------------------------------------------------
# DnfBackend
# ---------------------------------------------------------------------------


class TestDnfBackend:
    def _make(self):
        from ukm.core.backends.dnf import DnfBackend

        return DnfBackend()

    @mock.patch("shutil.which", return_value="/usr/bin/dnf")
    def test_is_available(self, _):
        assert self._make().is_available()

    @mock.patch("shutil.which", return_value=None)
    def test_not_available(self, _):
        assert not self._make().is_available()

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install(self, _, mock_run):
        rc, _, _ = self._make().install(["kernel-6.9.0"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "dnf" in cmd and "install" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_remove(self, _, mock_run):
        rc, _, _ = self._make().remove(["kernel-6.8.0"])
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_hold(self, _, mock_run):
        rc, _, _ = self._make().hold(["kernel-6.9.0"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "versionlock" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_unhold(self, _, mock_run):
        rc, _, _ = self._make().unhold(["kernel-6.9.0"])
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok())
    def test_is_installed_true(self, _):
        assert self._make().is_installed("kernel-6.9.0")

    @mock.patch("subprocess.run", return_value=_run_fail())
    def test_is_installed_false(self, _):
        assert not self._make().is_installed("kernel-6.9.0")

    @mock.patch("subprocess.run", return_value=_run_ok("kernel-6.9.0\n"))
    def test_is_held_true(self, _):
        assert self._make().is_held("kernel-6.9.0")

    @mock.patch("subprocess.run", return_value=_run_ok(""))
    def test_is_held_false(self, _):
        assert not self._make().is_held("kernel-6.9.0")

    @mock.patch("subprocess.run", return_value=_run_ok("kernel\nkernel-devel\n"))
    def test_installed_packages(self, _):
        pkgs = self._make().installed_packages()
        assert "kernel" in pkgs

    @mock.patch("subprocess.run", return_value=_run_fail())
    def test_installed_packages_failure(self, _):
        assert self._make().installed_packages() == []

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_refresh_cache(self, _, mock_run):
        rc, _, _ = self._make().refresh_cache()
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install_local(self, _, mock_run):
        rc, _, _ = self._make().install_local(["/tmp/kernel.rpm"])
        assert rc == 0


# ---------------------------------------------------------------------------
# ZypperBackend
# ---------------------------------------------------------------------------


class TestZypperBackend:
    def _make(self):
        from ukm.core.backends.zypper import ZypperBackend

        return ZypperBackend()

    @mock.patch("shutil.which", return_value="/usr/bin/zypper")
    def test_is_available(self, _):
        assert self._make().is_available()

    @mock.patch("shutil.which", return_value=None)
    def test_not_available(self, _):
        assert not self._make().is_available()

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install(self, _, mock_run):
        rc, _, _ = self._make().install(["kernel-default"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "zypper" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_remove(self, _, mock_run):
        rc, _, _ = self._make().remove(["kernel-default"])
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_hold(self, _, mock_run):
        rc, _, _ = self._make().hold(["kernel-default"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "zypper" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_unhold(self, _, mock_run):
        rc, _, _ = self._make().unhold(["kernel-default"])
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok("kernel-default-6.9.0"))
    def test_is_installed_true(self, _):
        assert self._make().is_installed("kernel-default")

    @mock.patch("subprocess.run", return_value=_run_fail())
    def test_is_installed_false(self, _):
        assert not self._make().is_installed("kernel-default")

    @mock.patch("subprocess.run", return_value=_run_ok("kernel-default\n"))
    def test_installed_packages(self, _):
        pkgs = self._make().installed_packages()
        assert "kernel-default" in pkgs

    @mock.patch("subprocess.run", return_value=_run_fail())
    def test_installed_packages_failure(self, _):
        assert self._make().installed_packages() == []

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_refresh_cache(self, _, mock_run):
        rc, _, _ = self._make().refresh_cache()
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install_local(self, _, mock_run):
        rc, _, _ = self._make().install_local(["/tmp/kernel.rpm"])
        assert rc == 0


# ---------------------------------------------------------------------------
# ApkBackend
# ---------------------------------------------------------------------------


class TestApkBackend:
    def _make(self):
        from ukm.core.backends.apk import ApkBackend

        return ApkBackend()

    @mock.patch("shutil.which", return_value="/sbin/apk")
    def test_is_available(self, _):
        assert self._make().is_available()

    @mock.patch("shutil.which", return_value=None)
    def test_not_available(self, _):
        assert not self._make().is_available()

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install(self, _, mock_run):
        rc, _, _ = self._make().install(["linux-lts"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "apk" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_remove(self, _, mock_run):
        rc, _, _ = self._make().remove(["linux-lts"])
        assert rc == 0

    @mock.patch("subprocess.run", side_effect=[_run_ok("linux-lts"), _run_ok()])
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_hold(self, _, mock_run):
        rc, _, _ = self._make().hold(["linux-lts"])
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_unhold(self, _, mock_run):
        rc, _, _ = self._make().unhold(["linux-lts"])
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok("linux-lts-6.6.0\n"))
    def test_is_installed_true(self, _):
        assert self._make().is_installed("linux-lts")

    @mock.patch("subprocess.run", return_value=_run_fail())
    def test_is_installed_false(self, _):
        assert not self._make().is_installed("linux-lts")

    @mock.patch("subprocess.run", return_value=_run_ok("linux-lts\nlinux-edge\n"))
    def test_installed_packages(self, _):
        pkgs = self._make().installed_packages()
        assert "linux-lts" in pkgs

    @mock.patch("subprocess.run", return_value=_run_fail())
    def test_installed_packages_failure(self, _):
        assert self._make().installed_packages() == []

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_refresh_cache(self, _, mock_run):
        rc, _, _ = self._make().refresh_cache()
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install_local(self, _, mock_run):
        rc, _, _ = self._make().install_local(["/tmp/linux-lts.apk"])
        assert rc == 0


# ---------------------------------------------------------------------------
# PacmanBackend (supplement existing tests)
# ---------------------------------------------------------------------------


class TestPacmanBackendExtra:
    def _make(self):
        from ukm.core.backends.pacman import PacmanBackend

        return PacmanBackend()

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_refresh_cache(self, _, mock_run):
        rc, _, _ = self._make().refresh_cache()
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "pacman" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install(self, _, mock_run):
        rc, _, _ = self._make().install(["linux-zen"])
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install_local(self, _, mock_run):
        rc, _, _ = self._make().install_local(["/tmp/linux-zen.pkg.tar.zst"])
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_remove(self, _, mock_run):
        rc, _, _ = self._make().remove(["linux-zen"])
        assert rc == 0

    @mock.patch("subprocess.run", return_value=_run_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_remove_purge(self, _, mock_run):
        self._make().remove(["linux-zen"], purge=True)
        cmd = mock_run.call_args[0][0]
        assert "-Rns" in cmd

    @mock.patch("subprocess.run", return_value=_run_ok())
    def test_is_installed_true(self, _):
        assert self._make().is_installed("linux-zen")

    @mock.patch("subprocess.run", return_value=_run_fail())
    def test_is_installed_false(self, _):
        assert not self._make().is_installed("linux-zen")

    @mock.patch("subprocess.run", return_value=_run_ok("linux-zen 6.9.0\nlinux 6.8.0\n"))
    def test_installed_packages(self, _):
        pkgs = self._make().installed_packages()
        assert len(pkgs) >= 1

    @mock.patch("subprocess.run", return_value=_run_fail())
    def test_installed_packages_failure(self, _):
        assert self._make().installed_packages() == []


# ---------------------------------------------------------------------------
# PackageBackend._run and .stream (base class)
# ---------------------------------------------------------------------------


class TestPackageBackendBase:
    def _make_concrete(self):
        """Create a minimal concrete subclass for testing base methods."""
        from ukm.core.backends.apt import AptBackend

        return AptBackend()

    @mock.patch("subprocess.run", return_value=_run_ok("hello\n"))
    def test_run_returns_tuple(self, _):
        from ukm.core.backends.base import PackageBackend

        rc, out, err = PackageBackend._run(["echo", "hello"])
        assert rc == 0
        assert out == "hello\n"

    def test_stream_yields_lines(self):
        from ukm.core.backends.base import PackageBackend

        proc = mock.MagicMock()
        proc.stdout = iter(["line1\n", "line2\n"])
        proc.__enter__ = lambda s: s
        proc.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch("subprocess.Popen", return_value=proc):
            list(PackageBackend._run.__func__ if False else
                         PackageBackend().stream(["echo", "hi"])
                         if False else [])
        # Just verify stream is callable without error via a real invocation
        backend = mock.MagicMock(spec=PackageBackend)
        backend.stream = PackageBackend.stream.__get__(backend, PackageBackend)
        with mock.patch("subprocess.Popen") as mock_popen:
            mock_proc = mock.MagicMock()
            mock_proc.stdout = iter(["a\n", "b\n"])
            mock_proc.__enter__ = lambda s: s
            mock_proc.__exit__ = mock.MagicMock(return_value=False)
            mock_popen.return_value.__enter__ = lambda s: mock_proc
            mock_popen.return_value.__exit__ = mock.MagicMock(return_value=False)
            # stream uses 'with Popen(...) as proc'
            result = list(PackageBackend.stream(backend, ["echo", "hi"]))
        assert result == ["a\n", "b\n"]
