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
