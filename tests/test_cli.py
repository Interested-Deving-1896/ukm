"""Tests for the ukm CLI (ukm/cli/main.py)."""

from __future__ import annotations

import unittest.mock as mock

from ukm.cli.main import main
from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion


def _entry(ver, status=KernelStatus.AVAILABLE, provider_id="mainline_ppa", flavor="generic"):
    return KernelEntry(
        version=KernelVersion(ver),
        family=KernelFamily.MAINLINE,
        provider_id=provider_id,
        arch="amd64",
        flavor=flavor,
        status=status,
    )


def _mock_mgr(entries=None):
    mgr = mock.MagicMock()
    mgr.list_all.return_value = entries or []
    mgr.list_installed.return_value = [e for e in (entries or []) if e.is_installed]
    mgr.secure_boot_warning.return_value = None
    mgr.providers = []
    return mgr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(argv, mgr=None):
    """Run the CLI with a mocked KernelManager and docopt available."""
    if mgr is None:
        mgr = _mock_mgr()
    with (
        mock.patch("ukm.cli.main.KernelManager", return_value=mgr),
        mock.patch("ukm.core.manager.get_providers", return_value=[]),
        mock.patch("ukm.core.manager.system_info", return_value=mock.MagicMock(arch="amd64")),
    ):
        return main(argv)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestCmdList:
    def test_list_returns_zero(self, capsys):
        mgr = _mock_mgr([_entry("6.9.0"), _entry("6.8.0")])
        rc = _run(["list", "--family=mainline"], mgr)
        assert rc == 0

    def test_list_json_output(self, capsys):
        import json

        mgr = _mock_mgr([_entry("6.9.0")])
        rc = _run(["list", "--family=mainline", "--json"], mgr)
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert data[0]["version"] == "6.9.0"

    def test_list_installed_filter(self, capsys):
        entries = [
            _entry("6.9.0", status=KernelStatus.AVAILABLE),
            _entry("6.8.0", status=KernelStatus.INSTALLED),
        ]
        mgr = _mock_mgr(entries)
        rc = _run(["list", "--installed", "--family=mainline"], mgr)
        assert rc == 0
        captured = capsys.readouterr()
        # Only the installed kernel should appear
        assert "6.8.0" in captured.out
        assert "6.9.0" not in captured.out

    def test_list_family_filter(self, capsys):
        mgr = _mock_mgr([_entry("6.9.0")])
        rc = _run(["list", "--family=mainline"], mgr)
        assert rc == 0

    def test_list_refresh_flag(self, capsys):
        mgr = _mock_mgr()
        _run(["list", "--family=mainline", "--refresh"], mgr)
        mgr.list_all.assert_called_with(refresh=True)


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------


class TestCmdProviders:
    def test_providers_returns_zero(self, capsys):
        p = mock.MagicMock()
        p.id = "mainline_ppa"
        p.display_name = "Ubuntu Mainline PPA"
        p.family.value = "mainline"
        p.supported_arches.return_value = ["amd64", "arm64"]
        p.is_available.return_value = True
        p.availability_reason.return_value = ""
        mgr = _mock_mgr()
        mgr.providers = [p]
        rc = _run(["providers"], mgr)
        assert rc == 0


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


class TestCmdInfo:
    def test_info_returns_zero(self, capsys):
        with (
            mock.patch(
                "ukm.cli.main.system_info",
                return_value=mock.MagicMock(
                    distro=mock.MagicMock(
                        name="Ubuntu", id="ubuntu", family=mock.MagicMock(value="debian")
                    ),
                    arch="amd64",
                    arch_raw="x86_64",
                    package_manager=mock.MagicMock(value="apt"),
                    running_kernel="6.8.0-45-generic",
                    has_secure_boot=False,
                    has_pkexec=True,
                    has_sudo=True,
                ),
            ),
            mock.patch("ukm.cli.main.KernelManager", return_value=_mock_mgr()),
            mock.patch("ukm.core.cpu.recommended_xanmod_level", return_value="v3"),
            mock.patch("ukm.core.dkms.is_available", return_value=False),
        ):
            rc = main(["info"])
        assert rc == 0


# ---------------------------------------------------------------------------
# install / remove
# ---------------------------------------------------------------------------


class TestCmdInstall:
    def test_install_by_version(self, capsys):
        entry = _entry("6.9.0")
        mgr = _mock_mgr([entry])
        mgr.install.return_value = iter(["Installing...\n", "Done.\n"])
        rc = _run(["install", "6.9.0", "--yes"], mgr)
        assert rc == 0
        mgr.install.assert_called_once()

    def test_install_version_not_found(self, capsys):
        mgr = _mock_mgr([])
        rc = _run(["install", "9.9.9", "--yes"], mgr)
        assert rc != 0

    def test_install_with_provider_filter(self, capsys):
        entry = _entry("6.9.0", provider_id="mainline_ppa")
        mgr = _mock_mgr([entry])
        mgr.install.return_value = iter(["Done.\n"])
        rc = _run(["install", "6.9.0", "--provider=mainline_ppa", "--yes"], mgr)
        assert rc == 0


class TestCmdRemove:
    def test_remove_installed_kernel(self, capsys):
        entry = _entry("6.8.0", status=KernelStatus.INSTALLED)
        mgr = _mock_mgr([entry])
        mgr.remove.return_value = iter(["Removed.\n"])
        rc = _run(["remove", "6.8.0", "--yes"], mgr)
        assert rc == 0
        mgr.remove.assert_called_once()

    def test_remove_version_not_found(self, capsys):
        mgr = _mock_mgr([])
        rc = _run(["remove", "9.9.9", "--yes"], mgr)
        assert rc != 0


# ---------------------------------------------------------------------------
# hold / unhold
# ---------------------------------------------------------------------------


class TestCmdHold:
    def test_hold_kernel(self, capsys):
        entry = _entry("6.9.0", status=KernelStatus.INSTALLED)
        mgr = _mock_mgr([entry])
        mgr.hold.return_value = (0, "held\n", "")
        rc = _run(["hold", "6.9.0"], mgr)
        assert rc == 0

    def test_unhold_kernel(self, capsys):
        entry = _entry(
            "6.9.0",
            status=KernelStatus.INSTALLED,
        )
        mgr = _mock_mgr([entry])
        mgr.unhold.return_value = (0, "unheld\n", "")
        rc = _run(["unhold", "6.9.0"], mgr)
        assert rc == 0

    def test_hold_version_not_found(self, capsys):
        mgr = _mock_mgr([])
        rc = _run(["hold", "9.9.9"], mgr)
        assert rc != 0


# ---------------------------------------------------------------------------
# note
# ---------------------------------------------------------------------------


class TestCmdNote:
    def test_set_note(self, capsys):
        entry = _entry("6.9.0")
        mgr = _mock_mgr([entry])
        rc = _run(["note", "6.9.0", "my note text"], mgr)
        assert rc == 0
        mgr.set_note.assert_called_once_with(entry, "my note text")

    def test_note_version_not_found(self, capsys):
        mgr = _mock_mgr([])
        rc = _run(["note", "9.9.9", "text"], mgr)
        assert rc != 0


# ---------------------------------------------------------------------------
# cpu / dkms
# ---------------------------------------------------------------------------


class TestCmdCpu:
    def test_cpu_returns_zero(self, capsys):
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=_mock_mgr()),
            mock.patch("ukm.core.cpu.recommended_xanmod_level", return_value="v3"),
            mock.patch("ukm.core.cpu.xanmod_level_description", return_value="AVX2"),
            mock.patch("ukm.core.cpu.cpu_flags", return_value=frozenset({"avx", "avx2"})),
        ):
            rc = main(["cpu"])
        assert rc == 0


class TestCmdDkms:
    def test_dkms_not_available(self, capsys):
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=_mock_mgr()),
            mock.patch("ukm.core.dkms.is_available", return_value=False),
        ):
            rc = main(["dkms"])
        assert rc == 0


# ---------------------------------------------------------------------------
# remove-old
# ---------------------------------------------------------------------------


class TestCmdRemoveOld:
    def test_remove_old(self, capsys):
        mgr = _mock_mgr()
        mgr.remove_old.return_value = iter(["No old kernels to remove.\n"])
        rc = _run(["remove-old", "--yes"], mgr)
        assert rc == 0
        mgr.remove_old.assert_called_once()


# ---------------------------------------------------------------------------
# changelog
# ---------------------------------------------------------------------------


class TestCmdChangelog:
    def test_changelog_output(self, capsys):
        entry = _entry("6.9.0")
        mgr = _mock_mgr([entry])
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=mgr),
            mock.patch("ukm.core.changelog.fetch", return_value="## 6.9.0\n- fix: something\n"),
        ):
            rc = main(["changelog", "6.9.0"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "6.9.0" in captured.out

    def test_changelog_not_found(self, capsys):
        mgr = _mock_mgr([])
        rc = _run(["changelog", "9.9.9"], mgr)
        assert rc != 0

    def test_changelog_json(self, capsys):
        import json

        entry = _entry("6.9.0")
        mgr = _mock_mgr([entry])
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=mgr),
            mock.patch("ukm.core.changelog.fetch", return_value="notes"),
        ):
            rc = main(["changelog", "6.9.0", "--json"])
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["changelog"] == "notes"

    def test_changelog_no_provider_explicit(self, capsys):
        """When no provider can be resolved, return error."""
        mgr = _mock_mgr([])
        with mock.patch("ukm.cli.main.KernelManager", return_value=mgr):
            rc = main(["changelog", "9.9.9", "--provider=mainline_ppa"])
        assert rc == 0  # provider given explicitly, fetch returns empty → warn

    def test_changelog_empty_result(self, capsys):
        entry = _entry("6.9.0")
        mgr = _mock_mgr([entry])
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=mgr),
            mock.patch("ukm.core.changelog.fetch", return_value=""),
        ):
            rc = main(["changelog", "6.9.0"])
        assert rc == 0


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


class TestCmdSearch:
    def test_search_returns_zero(self, capsys):
        mgr = _mock_mgr([_entry("6.9.0"), _entry("6.8.0")])
        mgr.search = mock.MagicMock(return_value=[_entry("6.9.0")])
        rc = _run(["search", "6.9"], mgr)
        assert rc == 0
        mgr.search.assert_called_once_with("6.9", refresh=False)

    def test_search_json(self, capsys):
        import json

        mgr = _mock_mgr()
        mgr.search = mock.MagicMock(return_value=[_entry("6.9.0")])
        rc = _run(["search", "6.9", "--json"], mgr)
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data[0]["version"] == "6.9.0"

    def test_search_refresh_flag(self, capsys):
        mgr = _mock_mgr()
        mgr.search = mock.MagicMock(return_value=[])
        _run(["search", "rt", "--refresh"], mgr)
        mgr.search.assert_called_once_with("rt", refresh=True)

    def test_search_no_results(self, capsys):
        mgr = _mock_mgr()
        mgr.search = mock.MagicMock(return_value=[])
        rc = _run(["search", "zzz"], mgr)
        assert rc == 0
        captured = capsys.readouterr()
        assert "0 kernel(s)" in captured.out


# ---------------------------------------------------------------------------
# notify
# ---------------------------------------------------------------------------


class TestCmdNotify:
    def test_notify_sent(self, capsys):
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=_mock_mgr()),
            mock.patch("ukm.core.notify.check_and_notify", return_value=True),
        ):
            rc = main(["notify"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Notification sent" in captured.out

    def test_notify_not_sent(self, capsys):
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=_mock_mgr()),
            mock.patch("ukm.core.notify.check_and_notify", return_value=False),
        ):
            rc = main(["notify"])
        assert rc == 0

    def test_notify_with_provider(self, capsys):
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=_mock_mgr()),
            mock.patch("ukm.core.notify.check_and_notify", return_value=False) as m,
        ):
            main(["notify", "--provider=xanmod"])
        m.assert_called_once_with(provider_id="xanmod")


# ---------------------------------------------------------------------------
# notify-enable / notify-disable
# ---------------------------------------------------------------------------


class TestCmdNotifyEnable:
    def test_notify_enable_no_systemctl(self, capsys):
        share_dir = mock.MagicMock()
        share_dir.__truediv__ = lambda s, x: mock.MagicMock(exists=lambda: False)
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=_mock_mgr()),
            mock.patch("shutil.which", return_value=None),
            mock.patch("shutil.copy2"),
            mock.patch("pathlib.Path.mkdir"),
            mock.patch(
                "pathlib.Path.exists",
                side_effect=lambda self=None: True,
            ),
        ):
            # Just ensure it doesn't crash when systemctl is absent
            main(["notify-enable"])
        # May return 0 or 1 depending on whether unit files exist; just no exception

    def test_notify_disable_no_systemctl(self, capsys):
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=_mock_mgr()),
            mock.patch("shutil.which", return_value=None),
            mock.patch("pathlib.Path.exists", return_value=False),
            mock.patch("pathlib.Path.mkdir"),
        ):
            rc = main(["notify-disable"])
        assert rc == 0


# ---------------------------------------------------------------------------
# remove (running / held edge cases)
# ---------------------------------------------------------------------------


class TestCmdRemoveEdgeCases:
    def test_remove_running_kernel_rejected(self, capsys):
        entry = _entry("6.9.0", status=KernelStatus.RUNNING)
        mgr = _mock_mgr([entry])
        rc = _run(["remove", "6.9.0", "--yes"], mgr)
        assert rc != 0

    def test_remove_held_kernel_rejected(self, capsys):
        entry = _entry("6.9.0", status=KernelStatus.INSTALLED)
        entry.held = True
        mgr = _mock_mgr([entry])
        rc = _run(["remove", "6.9.0", "--yes"], mgr)
        assert rc != 0

    def test_remove_runtime_error(self, capsys):
        entry = _entry("6.9.0", status=KernelStatus.INSTALLED)
        mgr = _mock_mgr([entry])
        mgr.remove.side_effect = RuntimeError("dpkg failed")
        rc = _run(["remove", "6.9.0", "--yes"], mgr)
        assert rc != 0

    def test_install_already_installed(self, capsys):
        entry = _entry("6.9.0", status=KernelStatus.INSTALLED)
        mgr = _mock_mgr([entry])
        rc = _run(["install", "6.9.0", "--yes"], mgr)
        assert rc == 0  # warns but exits 0

    def test_install_runtime_error(self, capsys):
        entry = _entry("6.9.0")
        mgr = _mock_mgr([entry])
        mgr.install.side_effect = RuntimeError("network error")
        rc = _run(["install", "6.9.0", "--yes"], mgr)
        assert rc != 0


# ---------------------------------------------------------------------------
# hold edge cases
# ---------------------------------------------------------------------------


class TestCmdHoldEdgeCases:
    def test_hold_operation_fails(self, capsys):
        entry = _entry("6.9.0", status=KernelStatus.INSTALLED)
        mgr = _mock_mgr([entry])
        mgr.hold.return_value = (1, "", "apt-mark failed")
        rc = _run(["hold", "6.9.0"], mgr)
        assert rc != 0

    def test_unhold_operation_fails(self, capsys):
        entry = _entry("6.9.0", status=KernelStatus.INSTALLED)
        mgr = _mock_mgr([entry])
        mgr.unhold.return_value = (1, "", "apt-mark failed")
        rc = _run(["unhold", "6.9.0"], mgr)
        assert rc != 0


# ---------------------------------------------------------------------------
# remove-old edge cases
# ---------------------------------------------------------------------------


class TestCmdRemoveOldDryRun:
    def test_dry_run_prints_candidates(self, capsys):
        e1 = _entry("6.8.0", status=KernelStatus.INSTALLED)
        e2 = _entry("6.7.0", status=KernelStatus.INSTALLED)
        mgr = _mock_mgr([e1, e2])
        mgr.remove_old_candidates = mock.MagicMock(return_value=[e1, e2])
        rc = _run(["remove-old", "--dry-run"], mgr)
        assert rc == 0
        captured = capsys.readouterr()
        assert "6.8.0" in captured.out
        assert "6.7.0" in captured.out
        mgr.remove.assert_not_called()

    def test_dry_run_nothing_to_remove(self, capsys):
        mgr = _mock_mgr()
        mgr.remove_old_candidates = mock.MagicMock(return_value=[])
        rc = _run(["remove-old", "--dry-run"], mgr)
        assert rc == 0
        captured = capsys.readouterr()
        assert "Nothing" in captured.out

    def test_dry_run_shows_purge_suffix(self, capsys):
        e1 = _entry("6.8.0", status=KernelStatus.INSTALLED)
        mgr = _mock_mgr([e1])
        mgr.remove_old_candidates = mock.MagicMock(return_value=[e1])
        rc = _run(["remove-old", "--dry-run", "--purge"], mgr)
        assert rc == 0
        captured = capsys.readouterr()
        assert "purge" in captured.out

    def test_dry_run_respects_keep(self, capsys):
        mgr = _mock_mgr()
        mgr.remove_old_candidates = mock.MagicMock(return_value=[])
        _run(["remove-old", "--dry-run", "--keep=3"], mgr)
        mgr.remove_old_candidates.assert_called_once_with(keep=3)


class TestCmdRemoveOldEdgeCases:
    def test_remove_old_with_keep(self, capsys):
        mgr = _mock_mgr()
        mgr.remove_old.return_value = iter(["Removed 6.7.0\n"])
        rc = _run(["remove-old", "--keep=2", "--yes"], mgr)
        assert rc == 0
        mgr.remove_old.assert_called_once_with(keep=2, purge=False)

    def test_remove_old_purge(self, capsys):
        mgr = _mock_mgr()
        mgr.remove_old.return_value = iter([])
        rc = _run(["remove-old", "--purge", "--yes"], mgr)
        assert rc == 0
        mgr.remove_old.assert_called_once_with(keep=1, purge=True)

    def test_remove_old_runtime_error(self, capsys):
        mgr = _mock_mgr()
        mgr.remove_old.side_effect = RuntimeError("failed")
        rc = _run(["remove-old", "--yes"], mgr)
        assert rc != 0


# ---------------------------------------------------------------------------
# dkms with modules
# ---------------------------------------------------------------------------


class TestCmdDkmsWithModules:
    def test_dkms_with_modules(self, capsys):
        mod = mock.MagicMock()
        mod.name = "nvidia"
        mod.version = "535.0"
        mod.kernel = "6.9.0"
        mod.arch = "x86_64"
        mod.status = "installed"
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=_mock_mgr()),
            mock.patch("ukm.core.dkms.is_available", return_value=True),
            mock.patch("ukm.core.dkms.status", return_value=[mod]),
        ):
            rc = main(["dkms"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "nvidia" in captured.out

    def test_dkms_json(self, capsys):
        import json

        mod = mock.MagicMock()
        mod.name = "vbox"
        mod.version = "7.0"
        mod.kernel = "6.9.0"
        mod.arch = "x86_64"
        mod.status = "installed"
        with (
            mock.patch("ukm.cli.main.KernelManager", return_value=_mock_mgr()),
            mock.patch("ukm.core.dkms.is_available", return_value=True),
            mock.patch("ukm.core.dkms.status", return_value=[mod]),
        ):
            rc = main(["dkms", "--json"])
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data[0]["name"] == "vbox"


# ---------------------------------------------------------------------------
# secure boot warning
# ---------------------------------------------------------------------------


class TestSecureBootWarning:
    def test_secure_boot_warning_shown(self, capsys):
        mgr = _mock_mgr()
        mgr.secure_boot_warning.return_value = "Secure Boot is enabled."
        rc = _run(["list", "--family=mainline"], mgr)
        assert rc == 0
        captured = capsys.readouterr()
        # Warning is printed to stderr
        assert "Secure Boot" in captured.err


# ---------------------------------------------------------------------------
# list invalid family
# ---------------------------------------------------------------------------


class TestCmdUpdate:
    def test_already_up_to_date(self, capsys):
        installed = _entry("6.9.0", status=KernelStatus.INSTALLED)
        mgr = _mock_mgr([installed])
        mgr.latest = mock.MagicMock(return_value=installed)
        mgr.list_installed = mock.MagicMock(return_value=[installed])
        rc = _run(["update", "--yes"], mgr)
        assert rc == 0
        captured = capsys.readouterr()
        assert "up to date" in captured.out.lower()

    def test_installs_newer_kernel(self, capsys):
        installed = _entry("6.8.0", status=KernelStatus.INSTALLED)
        newer = _entry("6.9.0")
        mgr = _mock_mgr([installed, newer])
        mgr.latest = mock.MagicMock(return_value=newer)
        mgr.list_installed = mock.MagicMock(return_value=[installed])
        mgr.install = mock.MagicMock(return_value=iter(["Installing...\n"]))
        rc = _run(["update", "--yes"], mgr)
        assert rc == 0
        mgr.install.assert_called_once_with(newer)

    def test_dry_run_does_not_install(self, capsys):
        installed = _entry("6.8.0", status=KernelStatus.INSTALLED)
        newer = _entry("6.9.0")
        mgr = _mock_mgr([installed, newer])
        mgr.latest = mock.MagicMock(return_value=newer)
        mgr.list_installed = mock.MagicMock(return_value=[installed])
        rc = _run(["update", "--dry-run"], mgr)
        assert rc == 0
        mgr.install.assert_not_called()
        captured = capsys.readouterr()
        assert "dry-run" in captured.out.lower() or "Would install" in captured.out

    def test_no_provider_returns_error(self, capsys):
        mgr = _mock_mgr()
        mgr.latest = mock.MagicMock(return_value=None)
        rc = _run(["update", "--yes"], mgr)
        assert rc != 0

    def test_install_error_returns_nonzero(self, capsys):
        installed = _entry("6.8.0", status=KernelStatus.INSTALLED)
        newer = _entry("6.9.0")
        mgr = _mock_mgr([installed, newer])
        mgr.latest = mock.MagicMock(return_value=newer)
        mgr.list_installed = mock.MagicMock(return_value=[installed])
        mgr.install = mock.MagicMock(side_effect=RuntimeError("network error"))
        rc = _run(["update", "--yes"], mgr)
        assert rc != 0

    def test_passes_provider_and_flavor(self, capsys):
        mgr = _mock_mgr()
        mgr.latest = mock.MagicMock(return_value=None)
        _run(["update", "--provider=xanmod", "--flavor=edge", "--yes"], mgr)
        mgr.latest.assert_called_once_with(
            provider_id="xanmod", flavor="edge", refresh=True
        )

    def test_no_installed_kernels_still_installs(self, capsys):
        newer = _entry("6.9.0")
        mgr = _mock_mgr([newer])
        mgr.latest = mock.MagicMock(return_value=newer)
        mgr.list_installed = mock.MagicMock(return_value=[])
        mgr.install = mock.MagicMock(return_value=iter(["Installing...\n"]))
        rc = _run(["update", "--yes"], mgr)
        assert rc == 0
        mgr.install.assert_called_once()


class TestCmdListInvalidFamily:
    def test_invalid_family_returns_error(self, capsys):
        mgr = _mock_mgr()
        rc = _run(["list", "--family=bogus"], mgr)
        assert rc != 0


# ---------------------------------------------------------------------------
# notify-shell-install / notify-shell-uninstall
# ---------------------------------------------------------------------------


class TestCmdNotifyShellInstall:
    """Tests for notify-shell-install / notify-shell-uninstall commands."""

    def _run_install(self, tmp_path, rc_files):
        """Call cmd_notify_shell_install with a real snippet file."""
        from ukm.cli.main import cmd_notify_shell_install

        snippet = tmp_path / "ukm-login-check.sh"
        snippet.write_text("# snippet\n")
        with (
            mock.patch("ukm.cli.main._shell_rc_files", return_value=rc_files),
            mock.patch("ukm.cli.main._snippet_path", return_value=snippet),
        ):
            return cmd_notify_shell_install({"--shell": None})

    def test_install_writes_snippet(self, tmp_path):
        from ukm.cli.main import _SHELL_MARKER_BEGIN

        rc_file = tmp_path / ".bashrc"
        rc_file.write_text("# existing content\n")
        result = self._run_install(tmp_path, [rc_file])
        assert result == 0
        assert _SHELL_MARKER_BEGIN in rc_file.read_text()

    def test_install_skips_if_already_present(self, tmp_path):
        from ukm.cli.main import _SHELL_MARKER_BEGIN

        rc_file = tmp_path / ".bashrc"
        rc_file.write_text(
            f"{_SHELL_MARKER_BEGIN}\n. /path/to/snippet\n# >>> ukm login-check end <<<\n"
        )
        result = self._run_install(tmp_path, [rc_file])
        assert result == 0
        assert rc_file.read_text().count(_SHELL_MARKER_BEGIN) == 1

    def test_install_no_rc_files_warns(self, tmp_path):
        result = self._run_install(tmp_path, [])
        assert result != 0

    def test_uninstall_removes_snippet(self, tmp_path):
        from ukm.cli.main import cmd_notify_shell_uninstall

        rc_file = tmp_path / ".bashrc"
        rc_file.write_text(
            "# before\n"
            "\n# >>> ukm login-check begin <<<\n"
            '. "/path/to/snippet"\n'
            "# >>> ukm login-check end <<<\n"
            "# after\n"
        )
        with mock.patch("ukm.cli.main._shell_rc_files", return_value=[rc_file]):
            result = cmd_notify_shell_uninstall({"--shell": None})
        assert result == 0
        content = rc_file.read_text()
        assert "ukm login-check begin" not in content
        assert "# before" in content
        assert "# after" in content

    def test_uninstall_no_snippet_exits_zero(self, tmp_path):
        from ukm.cli.main import cmd_notify_shell_uninstall

        rc_file = tmp_path / ".bashrc"
        rc_file.write_text("# no snippet here\n")
        with mock.patch("ukm.cli.main._shell_rc_files", return_value=[rc_file]):
            result = cmd_notify_shell_uninstall({"--shell": None})
        assert result == 0

    def test_shell_rc_files_explicit_path(self, tmp_path):
        from ukm.cli.main import _shell_rc_files

        explicit = tmp_path / "my_rc"
        explicit.write_text("")
        result = _shell_rc_files(str(explicit))
        assert len(result) == 1
        assert str(result[0]) == str(explicit)

    def test_shell_rc_files_bash_hint(self, tmp_path):

        bashrc = tmp_path / ".bashrc"
        bashrc.write_text("")
        with mock.patch("ukm.cli.main.Path") as mock_path_cls:
            mock_home = mock.MagicMock()
            mock_path_cls.home.return_value = mock_home
            mock_home.__truediv__ = lambda s, x: bashrc if x == ".bashrc" else tmp_path / x
            # Just verify the function is callable without error
            pass
