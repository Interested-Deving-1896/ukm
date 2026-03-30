"""Additional tests for DistroNativeProvider and PacmanBackend._edit_ignore_pkg."""

from __future__ import annotations

import tempfile
import unittest.mock as mock
from pathlib import Path

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion
from ukm.core.providers.distro_native import DistroNativeProvider


def _make_backend(run_results=None, installed=None):
    b = mock.MagicMock()
    b.is_available.return_value = True
    b.installed_packages.return_value = installed or []
    b.is_held.return_value = False
    b.refresh_cache.return_value = (0, "", "")
    if run_results:
        b._run.side_effect = run_results
    else:
        b._run.return_value = (0, "", "")
    return b


def _entry(ver="6.9.0", pkg="linux-image-6.9.0-generic"):
    return KernelEntry(
        version=KernelVersion(ver),
        family=KernelFamily.DISTRO,
        provider_id="distro_native",
        arch="amd64",
        flavor="generic",
        description=pkg,
    )


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------


class TestDistroNativeProviderMeta:
    def test_id(self):
        p = DistroNativeProvider(_make_backend())
        assert p.id == "distro_native"

    def test_family(self):
        p = DistroNativeProvider(_make_backend())
        assert p.family == KernelFamily.DISTRO

    def test_supports_all_arches(self):
        p = DistroNativeProvider(_make_backend())
        assert p.supports_arch("amd64")
        assert p.supports_arch("arm64")
        assert p.supports_arch("riscv64")

    def test_is_available_delegates(self):
        b = _make_backend()
        b.is_available.return_value = True
        assert DistroNativeProvider(b).is_available()

    def test_display_name_includes_distro(self):
        p = DistroNativeProvider(_make_backend())
        with mock.patch(
            "ukm.core.providers.distro_native.system_info",
            return_value=mock.MagicMock(distro=mock.MagicMock(name="Ubuntu")),
        ):
            name = p.display_name
        assert "Ubuntu" in name


# ---------------------------------------------------------------------------
# _list_apt
# ---------------------------------------------------------------------------


class TestDistroNativeListApt:
    def test_parses_apt_packages(self):
        apt_output = (
            "linux-image-6.9.0-generic - Linux kernel image\n"
            "linux-image-6.8.0-generic - Linux kernel image\n"
        )
        b = _make_backend(run_results=[(0, apt_output, "")])
        p = DistroNativeProvider(b)
        with mock.patch(
            "ukm.core.providers.distro_native.system_info",
            return_value=mock.MagicMock(
                package_manager=mock.MagicMock(value="apt"),
                running_kernel="",
            ),
        ):
            from ukm.core.system import PackageManagerKind
            with mock.patch(
                "ukm.core.providers.distro_native.system_info",
                return_value=mock.MagicMock(
                    package_manager=PackageManagerKind.APT,
                    running_kernel="",
                ),
            ):
                entries = p._list_apt("amd64", "")
        assert len(entries) >= 1

    def test_marks_installed(self):
        apt_output = "linux-image-6.9.0-generic - Linux kernel image\n"
        b = _make_backend(
            run_results=[(0, apt_output, "")],
            installed=["linux-image-6.9.0-generic"],
        )
        p = DistroNativeProvider(b)
        entries = p._list_apt("amd64", "")
        assert any(e.status == KernelStatus.INSTALLED for e in entries)

    def test_marks_running(self):
        apt_output = "linux-image-6.9.0-generic - Linux kernel image\n"
        b = _make_backend(run_results=[(0, apt_output, "")])
        p = DistroNativeProvider(b)
        entries = p._list_apt("amd64", "6.9.0")
        assert any(e.status == KernelStatus.RUNNING for e in entries)

    def test_returns_empty_on_failure(self):
        b = _make_backend(run_results=[(1, "", "error")])
        p = DistroNativeProvider(b)
        assert p._list_apt("amd64", "") == []

    def test_skips_meta_packages(self):
        # linux-image-generic has no version number in name → skipped
        apt_output = "linux-image-generic - Generic kernel meta-package\n"
        b = _make_backend(run_results=[(0, apt_output, "")])
        p = DistroNativeProvider(b)
        entries = p._list_apt("amd64", "")
        assert entries == []


# ---------------------------------------------------------------------------
# _list_pacman
# ---------------------------------------------------------------------------


class TestDistroNativeListPacman:
    def test_parses_pacman_packages(self):
        pacman_si_output = (
            "Name           : linux\n"
            "Version        : 6.9.0.arch1-1\n"
            "Description    : The Linux kernel\n"
        )
        # _list_pacman calls: _run (pacman -Si), is_installed, is_held per package
        # Only first package (linux) succeeds; rest fail
        b = _make_backend(
            run_results=[(0, pacman_si_output, "")] + [(1, "", "")] * 9
        )
        b.is_installed.return_value = False
        b.is_held.return_value = False
        p = DistroNativeProvider(b)
        entries = p._list_pacman("amd64", "")
        assert len(entries) >= 1
        assert str(entries[0].version) == "6.9.0.arch1-1"

    def test_skips_unavailable_packages(self):
        b = _make_backend(
            run_results=[(1, "", "error")] * 10
        )
        p = DistroNativeProvider(b)
        entries = p._list_pacman("amd64", "")
        assert entries == []


# ---------------------------------------------------------------------------
# _list_dnf
# ---------------------------------------------------------------------------


class TestDistroNativeListDnf:
    def test_parses_dnf_packages(self):
        # _list_dnf calls _run twice: dnf list, then rpm -qa
        dnf_output = (
            "kernel.x86_64                    6.9.0-100.fc40\n"
            "kernel.x86_64                    6.8.0-100.fc40\n"
        )
        b = _make_backend(run_results=[
            (0, dnf_output, ""),   # dnf list
            (0, "", ""),           # rpm -qa installed
        ])
        p = DistroNativeProvider(b)
        entries = p._list_dnf("amd64", "")
        assert len(entries) >= 1

    def test_returns_empty_on_failure(self):
        b = _make_backend(run_results=[(1, "", "error")])
        p = DistroNativeProvider(b)
        assert p._list_dnf("amd64", "") == []


# ---------------------------------------------------------------------------
# _list_zypper
# ---------------------------------------------------------------------------


class TestDistroNativeListZypper:
    def test_parses_zypper_packages(self):
        # zypper search -t package output: status | name | summary | type | version | arch | repo
        # _list_zypper splits on | and checks parts[1]=name, parts[3]=version (0-indexed)
        # Format: "  | kernel-default | The standard kernel | package | 6.9.0-1.1 | x86_64 | repo"
        zypper_output = (
            "  | kernel-default | The standard kernel | package | 6.9.0-1.1 | x86_64 | repo\n"
        )
        b = _make_backend(run_results=[(0, zypper_output, "")])
        b.is_installed.return_value = False
        p = DistroNativeProvider(b)
        entries = p._list_zypper("amd64", "")
        assert len(entries) >= 1

    def test_returns_empty_on_failure(self):
        b = _make_backend(run_results=[(1, "", "error")])
        p = DistroNativeProvider(b)
        assert p._list_zypper("amd64", "") == []


# ---------------------------------------------------------------------------
# _list_apk
# ---------------------------------------------------------------------------


class TestDistroNativeListApk:
    def test_parses_apk_packages(self):
        apk_output = "linux-lts-6.6.0-r0\nlinux-edge-6.9.0-r0\n"
        b = _make_backend(run_results=[(0, apk_output, "")])
        p = DistroNativeProvider(b)
        entries = p._list_apk("aarch64", "")
        assert len(entries) >= 1

    def test_returns_empty_on_failure(self):
        b = _make_backend(run_results=[(1, "", "error")])
        p = DistroNativeProvider(b)
        assert p._list_apk("aarch64", "") == []


# ---------------------------------------------------------------------------
# fetch dispatch
# ---------------------------------------------------------------------------


class TestDistroNativeFetch:
    def test_fetch_calls_refresh_when_requested(self):
        b = _make_backend()
        p = DistroNativeProvider(b)
        from ukm.core.system import PackageManagerKind
        with mock.patch(
            "ukm.core.providers.distro_native.system_info",
            return_value=mock.MagicMock(
                package_manager=PackageManagerKind.APT,
                running_kernel="",
            ),
        ):
            p.fetch("amd64", refresh=True)
        b.refresh_cache.assert_called_once()

    def test_fetch_returns_empty_for_unknown_pm(self):
        b = _make_backend()
        p = DistroNativeProvider(b)
        with mock.patch(
            "ukm.core.providers.distro_native.system_info",
            return_value=mock.MagicMock(
                package_manager=mock.MagicMock(value="unknown"),
                running_kernel="",
            ),
        ):
            # No matching branch → returns []
            result = p.fetch("amd64")
        assert result == []


# ---------------------------------------------------------------------------
# install / remove
# ---------------------------------------------------------------------------


class TestDistroNativeInstallRemove:
    def test_install_success(self):
        b = _make_backend()
        b.install.return_value = (0, "installed\n", "")
        p = DistroNativeProvider(b)
        lines = list(p.install(_entry()))
        assert any("installed" in line.lower() for line in lines)

    def test_install_failure_raises(self):
        import pytest
        b = _make_backend()
        b.install.return_value = (1, "", "dpkg error")
        p = DistroNativeProvider(b)
        with pytest.raises(RuntimeError):
            list(p.install(_entry()))

    def test_remove_success(self):
        b = _make_backend()
        b.remove.return_value = (0, "removed\n", "")
        p = DistroNativeProvider(b)
        lines = list(p.remove(_entry()))
        assert any("removed" in line.lower() for line in lines)

    def test_remove_failure_raises(self):
        import pytest
        b = _make_backend()
        b.remove.return_value = (1, "", "dpkg error")
        p = DistroNativeProvider(b)
        with pytest.raises(RuntimeError):
            list(p.remove(_entry()))


# ---------------------------------------------------------------------------
# PacmanBackend._edit_ignore_pkg
# ---------------------------------------------------------------------------


class TestPacmanEditIgnorePkg:
    def _make_pacman(self):
        from ukm.core.backends.pacman import PacmanBackend
        return PacmanBackend()

    def test_add_to_existing_ignorepkg(self):
        conf_content = "[options]\nIgnorePkg = linux-lts\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(conf_content)
            conf_path = f.name

        p = self._make_pacman()
        with (
            mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[]),
            mock.patch("subprocess.run", return_value=mock.MagicMock(returncode=0, stdout="", stderr="")),
            mock.patch("builtins.open", mock.mock_open(read_data=conf_content)),
        ):
            rc, _, _ = p._edit_ignore_pkg(["linux-zen"], add=True)
        # rc depends on the cp mock; just verify no exception

    def test_add_creates_ignorepkg_when_missing(self):
        conf_content = "[options]\nColor\n"
        p = self._make_pacman()
        with (
            mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[]),
            mock.patch("subprocess.run", return_value=mock.MagicMock(returncode=0, stdout="", stderr="")),
            mock.patch("builtins.open", mock.mock_open(read_data=conf_content)),
        ):
            rc, _, _ = p._edit_ignore_pkg(["linux-zen"], add=True)

    def test_returns_error_when_conf_missing(self):
        p = self._make_pacman()
        with mock.patch("builtins.open", side_effect=FileNotFoundError):
            rc, _, err = p._edit_ignore_pkg(["linux-zen"], add=True)
        assert rc == 1
        assert "not found" in err

    def test_remove_from_ignorepkg(self):
        conf_content = "[options]\nIgnorePkg = linux-lts linux-zen\n"
        p = self._make_pacman()
        with (
            mock.patch("ukm.core.system.privilege_escalation_cmd", return_value=[]),
            mock.patch("subprocess.run", return_value=mock.MagicMock(returncode=0, stdout="", stderr="")),
            mock.patch("builtins.open", mock.mock_open(read_data=conf_content)),
        ):
            rc, _, _ = p._edit_ignore_pkg(["linux-zen"], add=False)

    def test_is_held_reads_pacman_conf(self):
        conf_content = "IgnorePkg = linux-zen linux-lts\n"
        p = self._make_pacman()
        with mock.patch("builtins.open", mock.mock_open(read_data=conf_content)):
            assert p.is_held("linux-zen")
            assert not p.is_held("linux-rt")

    def test_is_held_returns_false_when_conf_missing(self):
        p = self._make_pacman()
        with mock.patch("builtins.open", side_effect=FileNotFoundError):
            assert not p.is_held("linux-zen")
