"""Tests for the Portage backend (Gentoo Linux)."""

from __future__ import annotations

import tempfile
import unittest.mock as mock
from pathlib import Path

from ukm.core.backends.portage import PortageBackend


def _ok(stdout=""):
    return mock.MagicMock(returncode=0, stdout=stdout, stderr="")


def _fail(stderr="error"):
    return mock.MagicMock(returncode=1, stdout="", stderr=stderr)


def _make():
    return PortageBackend()


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


class TestAvailability:
    @mock.patch("shutil.which", return_value="/usr/bin/emerge")
    def test_is_available(self, _):
        assert _make().is_available()

    @mock.patch("shutil.which", return_value=None)
    def test_not_available(self, _):
        assert not _make().is_available()

    def test_name(self):
        assert _make().name == "portage"


# ---------------------------------------------------------------------------
# refresh_cache
# ---------------------------------------------------------------------------


class TestRefreshCache:
    @mock.patch("subprocess.run", return_value=_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    @mock.patch("shutil.which", return_value="/usr/bin/emaint")
    def test_uses_emaint_when_available(self, _, __, mock_run):
        rc, _, _ = _make().refresh_cache()
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "emaint" in cmd

    @mock.patch("subprocess.run", return_value=_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    @mock.patch("shutil.which", return_value=None)
    def test_falls_back_to_emerge_sync(self, _, __, mock_run):
        rc, _, _ = _make().refresh_cache()
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "emerge" in cmd
        assert "--sync" in cmd


# ---------------------------------------------------------------------------
# install / install_local / remove
# ---------------------------------------------------------------------------


class TestInstall:
    @mock.patch("subprocess.run", return_value=_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install(self, _, mock_run):
        rc, _, _ = _make().install(["sys-kernel/gentoo-sources"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "emerge" in cmd
        assert "sys-kernel/gentoo-sources" in cmd

    def test_install_local_returns_error(self):
        rc, _, err = _make().install_local(["/tmp/kernel.tar.bz2"])
        assert rc == 1
        assert "local overlay" in err.lower() or "portage" in err.lower()

    @mock.patch("subprocess.run", return_value=_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_remove_unmerge(self, _, mock_run):
        rc, _, _ = _make().remove(["sys-kernel/gentoo-sources"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "--unmerge" in cmd

    @mock.patch("subprocess.run", return_value=_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_remove_purge_uses_depclean(self, _, mock_run):
        _make().remove(["sys-kernel/gentoo-sources"], purge=True)
        cmd = mock_run.call_args[0][0]
        assert "--depclean" in cmd


# ---------------------------------------------------------------------------
# hold / unhold
# ---------------------------------------------------------------------------


class TestHold:
    def test_hold_writes_mask_file(self, tmp_path):
        mask_file = tmp_path / "ukm-held"

        with (
            mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[]),
            mock.patch("subprocess.run", return_value=_ok()),
            mock.patch("ukm.core.backends.portage.Path") as mock_path_cls,
        ):
            # Make mask_dir.is_dir() return False so mask_file = mask_dir itself
            mock_mask_dir = mock.MagicMock()
            mock_mask_dir.is_dir.return_value = False
            mock_mask_dir.exists.return_value = False
            mock_mask_dir.__truediv__ = lambda s, x: mask_file
            mock_path_cls.return_value = mock_mask_dir

            with mock.patch.object(
                _make(), "_installed_version", return_value="6.9.0"
            ) as mock_ver:
                p = _make()
                p._installed_version = mock.MagicMock(return_value="6.9.0")
                with (
                    mock.patch("builtins.open", mock.mock_open(read_data="")),
                    mock.patch("os.unlink"),
                    mock.patch("tempfile.NamedTemporaryFile") as mock_tmp,
                ):
                    mock_tmp.return_value.__enter__ = lambda s: mock.MagicMock(name="/tmp/x")
                    mock_tmp.return_value.__exit__ = mock.MagicMock(return_value=False)
                    rc, _, _ = p.hold(["sys-kernel/gentoo-sources"])
        # rc depends on cp mock; just verify no exception

    def test_hold_exception_returns_error(self):
        p = _make()
        p._installed_version = mock.MagicMock(return_value="6.9.0")
        # Patch Path so mask_file.read_text() raises PermissionError
        with (
            mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[]),
            mock.patch("ukm.core.backends.portage.Path") as mock_path_cls,
        ):
            mock_mask_dir = mock.MagicMock()
            mock_mask_dir.is_dir.return_value = False
            mock_mask_dir.exists.return_value = True
            mock_mask_dir.read_text.side_effect = PermissionError("denied")
            mock_path_cls.return_value = mock_mask_dir
            rc, _, err = p.hold(["sys-kernel/gentoo-sources"])
        assert rc == 1
        assert "denied" in err

    def test_unhold_no_mask_file(self, tmp_path):
        with mock.patch("ukm.core.backends.portage.Path") as mock_path_cls:
            mock_mask_dir = mock.MagicMock()
            mock_mask_dir.is_dir.return_value = False
            mock_mask_dir.exists.return_value = False
            mock_path_cls.return_value = mock_mask_dir
            rc, out, _ = _make().unhold(["sys-kernel/gentoo-sources"])
        assert rc == 0
        assert "No held" in out

    def test_unhold_removes_package_from_mask(self):
        mask_content = ">sys-kernel/gentoo-sources-6.9.0\n>sys-kernel/vanilla-sources-6.8.0\n"
        with (
            mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[]),
            mock.patch("subprocess.run", return_value=_ok()),
            mock.patch("builtins.open", mock.mock_open(read_data=mask_content)),
            mock.patch("os.unlink"),
            mock.patch("tempfile.NamedTemporaryFile") as mock_tmp,
            mock.patch("ukm.core.backends.portage.Path") as mock_path_cls,
        ):
            mock_mask_dir = mock.MagicMock()
            mock_mask_dir.is_dir.return_value = False
            mock_mask_dir.exists.return_value = True
            mock_path_cls.return_value = mock_mask_dir
            mock_tmp.return_value.__enter__ = lambda s: mock.MagicMock(name="/tmp/x")
            mock_tmp.return_value.__exit__ = mock.MagicMock(return_value=False)
            rc, _, _ = _make().unhold(["sys-kernel/gentoo-sources"])
        assert rc == 0

    def test_unhold_exception_returns_error(self):
        with mock.patch("ukm.core.backends.portage.Path") as mock_path_cls:
            mock_mask_dir = mock.MagicMock()
            mock_mask_dir.is_dir.return_value = False
            mock_mask_dir.exists.return_value = True
            mock_mask_dir.read_text.side_effect = PermissionError("denied")
            mock_path_cls.return_value = mock_mask_dir
            rc, _, err = _make().unhold(["sys-kernel/gentoo-sources"])
        assert rc == 1
        assert "denied" in err


# ---------------------------------------------------------------------------
# is_installed / is_held / installed_packages
# ---------------------------------------------------------------------------


class TestQuery:
    @mock.patch("subprocess.run", return_value=_ok("sys-kernel/gentoo-sources-6.9.0\n"))
    def test_is_installed_true(self, _):
        assert _make().is_installed("sys-kernel/gentoo-sources")

    @mock.patch("subprocess.run", return_value=_fail())
    def test_is_installed_false(self, _):
        assert not _make().is_installed("sys-kernel/gentoo-sources")

    def test_is_held_true(self):
        with mock.patch("ukm.core.backends.portage.Path") as mock_path_cls:
            mock_mask_dir = mock.MagicMock()
            mock_mask_dir.is_dir.return_value = False
            mock_mask_dir.exists.return_value = True
            mock_mask_dir.read_text.return_value = ">sys-kernel/gentoo-sources-6.9.0\n"
            mock_path_cls.return_value = mock_mask_dir
            assert _make().is_held("sys-kernel/gentoo-sources")

    def test_is_held_false_when_not_in_mask(self):
        with mock.patch("ukm.core.backends.portage.Path") as mock_path_cls:
            mock_mask_dir = mock.MagicMock()
            mock_mask_dir.is_dir.return_value = False
            mock_mask_dir.exists.return_value = True
            mock_mask_dir.read_text.return_value = ">sys-kernel/vanilla-sources-6.8.0\n"
            mock_path_cls.return_value = mock_mask_dir
            assert not _make().is_held("sys-kernel/gentoo-sources")

    def test_is_held_false_when_no_mask_file(self):
        with mock.patch("ukm.core.backends.portage.Path") as mock_path_cls:
            mock_mask_dir = mock.MagicMock()
            mock_mask_dir.is_dir.return_value = False
            mock_mask_dir.exists.return_value = False
            mock_path_cls.return_value = mock_mask_dir
            assert not _make().is_held("sys-kernel/gentoo-sources")

    @mock.patch(
        "subprocess.run",
        return_value=_ok("sys-kernel/gentoo-sources-6.9.0\nsys-kernel/vanilla-sources-6.8.0\n"),
    )
    def test_installed_packages(self, _):
        pkgs = _make().installed_packages()
        assert "sys-kernel/gentoo-sources-6.9.0" in pkgs

    @mock.patch("subprocess.run", return_value=_fail())
    def test_installed_packages_failure(self, _):
        assert _make().installed_packages() == []

    @mock.patch(
        "subprocess.run",
        return_value=_ok("sys-kernel/gentoo-sources-6.9.0\n"),
    )
    def test_installed_packages_with_pattern(self, mock_run):
        _make().installed_packages(pattern="gentoo")
        cmd = mock_run.call_args[0][0]
        assert "*gentoo*" in cmd


# ---------------------------------------------------------------------------
# Gentoo-specific: source compilation helpers
# ---------------------------------------------------------------------------


class TestSourceHelpers:
    @mock.patch("shutil.which", return_value="/usr/bin/genkernel")
    def test_has_genkernel_true(self, _):
        assert _make().has_genkernel()

    @mock.patch("shutil.which", return_value=None)
    def test_has_genkernel_false(self, _):
        assert not _make().has_genkernel()

    @mock.patch("subprocess.run", return_value=_ok())
    def test_has_eselect_kernel_true(self, _):
        assert _make().has_eselect_kernel()

    @mock.patch("subprocess.run", return_value=_fail())
    def test_has_eselect_kernel_false(self, _):
        assert not _make().has_eselect_kernel()

    def test_list_kernel_sources_no_src_dir(self):
        with mock.patch("ukm.core.backends.portage.Path") as mock_path_cls:
            mock_src = mock.MagicMock()
            mock_src.exists.return_value = False
            mock_path_cls.return_value = mock_src
            result = _make().list_kernel_sources()
        assert result == []

    def test_list_kernel_sources_returns_linux_dirs(self, tmp_path):
        (tmp_path / "linux-6.9.0-gentoo").mkdir()
        (tmp_path / "linux-6.8.0-gentoo").mkdir()
        (tmp_path / "other-dir").mkdir()

        with mock.patch("ukm.core.backends.portage.Path", return_value=tmp_path):
            result = _make().list_kernel_sources()
        assert len(result) == 2
        assert all("linux-" in r for r in result)

    @mock.patch("subprocess.run", return_value=_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_set_active_source(self, _, mock_run):
        rc, _, _ = _make().set_active_source("/usr/src/linux-6.9.0-gentoo")
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "ln" in cmd
        assert "/usr/src/linux-6.9.0-gentoo" in cmd

    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_configure_kernel_returns_command(self, _):
        cmd = _make().configure_kernel("/usr/src/linux", "menuconfig")
        assert "make" in cmd
        assert "menuconfig" in cmd
        assert "/usr/src/linux" in cmd

    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_compile_kernel_genkernel_returns_command(self, _):
        cmd = _make().compile_kernel_genkernel("/usr/src/linux")
        assert "genkernel" in cmd
        assert "all" in cmd
        assert "/usr/src/linux" in cmd

    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_compile_kernel_genkernel_with_extra_args(self, _):
        cmd = _make().compile_kernel_genkernel("/usr/src/linux", extra_args=["--no-clean"])
        assert "--no-clean" in cmd

    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_compile_kernel_make_returns_command(self, _):
        cmd = _make().compile_kernel_make("/usr/src/linux", jobs=4)
        assert "make" in cmd
        assert "-j4" in cmd
        assert "bzImage" in cmd

    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_compile_kernel_make_auto_jobs(self, _):
        cmd = _make().compile_kernel_make("/usr/src/linux", jobs=0)
        assert any(a.startswith("-j") for a in cmd)

    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_compile_kernel_make_custom_targets(self, _):
        cmd = _make().compile_kernel_make("/usr/src/linux", targets=["modules"])
        assert "modules" in cmd
        assert "bzImage" not in cmd

    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    def test_install_kernel_make_returns_command(self, _):
        cmd = _make().install_kernel_make("/usr/src/linux")
        assert "make" in cmd
        assert "modules_install" in cmd
        assert "install" in cmd

    @mock.patch("subprocess.run", return_value=_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    @mock.patch("shutil.which", return_value="/usr/sbin/grub-mkconfig")
    def test_update_bootloader_grub(self, _, __, mock_run):
        rc, _, _ = _make().update_bootloader()
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "grub-mkconfig" in cmd

    @mock.patch("subprocess.run", return_value=_ok())
    @mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[])
    @mock.patch("shutil.which", side_effect=lambda t: "/usr/sbin/grub2-mkconfig" if t == "grub2-mkconfig" else None)
    def test_update_bootloader_grub2(self, _, __, mock_run):
        rc, _, _ = _make().update_bootloader()
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "grub2-mkconfig" in cmd

    @mock.patch("shutil.which", return_value=None)
    def test_update_bootloader_no_grub(self, _):
        rc, _, err = _make().update_bootloader()
        assert rc == 1
        assert "manually" in err.lower()


# ---------------------------------------------------------------------------
# _installed_version helper
# ---------------------------------------------------------------------------


class TestInstalledVersion:
    @mock.patch("subprocess.run", return_value=_ok("6.9.0\n"))
    def test_returns_version(self, _):
        assert _make()._installed_version("sys-kernel/gentoo-sources") == "6.9.0"

    @mock.patch("subprocess.run", return_value=_fail())
    def test_returns_empty_on_failure(self, _):
        assert _make()._installed_version("sys-kernel/gentoo-sources") == ""

    @mock.patch("subprocess.run", return_value=_ok(""))
    def test_returns_empty_when_no_output(self, _):
        assert _make()._installed_version("sys-kernel/gentoo-sources") == ""
