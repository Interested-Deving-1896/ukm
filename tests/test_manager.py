"""Tests for KernelManager."""

from __future__ import annotations

import json
import tempfile
import unittest.mock as mock
from pathlib import Path

import pytest

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion
from ukm.core.manager import KernelManager


def make_entry(
    version="6.9.0", status=KernelStatus.AVAILABLE, held=False, provider_id="mainline_ppa"
):
    return KernelEntry(
        version=KernelVersion(version),
        family=KernelFamily.MAINLINE,
        provider_id=provider_id,
        arch="amd64",
        flavor="generic",
        status=status,
        held=held,
    )


class _mgr_ctx:
    """Context manager that patches KernelManager construction."""

    def __init__(self, tmp_path, providers=None):
        self._state_file = tmp_path / "state.json"
        self._providers = providers or []
        self._patches = [
            mock.patch("ukm.core.manager._STATE_FILE", self._state_file),
            mock.patch("ukm.core.manager.get_providers", return_value=self._providers),
            mock.patch("ukm.core.manager.system_info", return_value=mock.MagicMock(arch="amd64")),
        ]

    def __enter__(self):
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *args):
        for p in reversed(self._patches):
            p.stop()


def _mock_provider(entries=None, provider_id="mainline_ppa", available=True):
    p = mock.MagicMock()
    p.id = provider_id
    p.display_name = provider_id
    p.fetch.return_value = entries or []
    p.is_available.return_value = available
    p.availability_reason.return_value = "not available"
    p.install.return_value = iter(["installing\n"])
    p.remove.return_value = iter(["removing\n"])
    p.hold.return_value = (0, "held\n", "")
    p.unhold.return_value = (0, "unheld\n", "")
    return p


class TestKernelManager:
    def _make_manager(self, entries=None, tmp_state=None):
        """Create a KernelManager with mocked providers and state file."""
        mgr = mock.MagicMock(spec=KernelManager)
        return mgr

    def test_notes_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with (
                mock.patch("ukm.core.manager._STATE_FILE", state_file),
                mock.patch("ukm.core.manager.get_providers", return_value=[]),
            ):
                mgr = KernelManager()
                entry = make_entry()
                mgr.set_note(entry, "test note")

                assert state_file.exists()
                state = json.loads(state_file.read_text())
                key = mgr._state_key(entry)
                assert state["notes"][key] == "test note"

    def test_note_retrieved_after_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with (
                mock.patch("ukm.core.manager._STATE_FILE", state_file),
                mock.patch("ukm.core.manager.get_providers", return_value=[]),
            ):
                mgr = KernelManager()
                entry = make_entry()
                mgr.set_note(entry, "persistent note")

            # Reload
            with (
                mock.patch("ukm.core.manager._STATE_FILE", state_file),
                mock.patch("ukm.core.manager.get_providers", return_value=[]),
            ):
                mgr2 = KernelManager()
                assert mgr2.get_note(entry) == "persistent note"

    def test_remove_running_kernel_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            with (
                mock.patch("ukm.core.manager._STATE_FILE", state_file),
                mock.patch("ukm.core.manager.get_providers", return_value=[]),
            ):
                mgr = KernelManager()
                entry = make_entry(status=KernelStatus.RUNNING)
                import pytest

                with pytest.raises(RuntimeError, match="running"):
                    list(mgr.remove(entry))

    def test_remove_held_kernel_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            with (
                mock.patch("ukm.core.manager._STATE_FILE", state_file),
                mock.patch("ukm.core.manager.get_providers", return_value=[]),
            ):
                mgr = KernelManager()
                entry = make_entry(status=KernelStatus.INSTALLED, held=True)
                import pytest

                with pytest.raises(RuntimeError, match="locked"):
                    list(mgr.remove(entry))

    def test_secure_boot_warning_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            with (
                mock.patch("ukm.core.manager._STATE_FILE", state_file),
                mock.patch("ukm.core.manager.get_providers", return_value=[]),
                mock.patch("ukm.core.manager.system_info") as mock_si,
            ):
                mock_si.return_value.has_secure_boot = True
                mgr = KernelManager()
                assert mgr.secure_boot_warning() is not None
                assert "Secure Boot" in mgr.secure_boot_warning()

    def test_no_secure_boot_warning_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            with (
                mock.patch("ukm.core.manager._STATE_FILE", state_file),
                mock.patch("ukm.core.manager.get_providers", return_value=[]),
                mock.patch("ukm.core.manager.system_info") as mock_si,
            ):
                mock_si.return_value.has_secure_boot = False
                mgr = KernelManager()
                assert mgr.secure_boot_warning() is None

    def test_state_key_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            with (
                mock.patch("ukm.core.manager._STATE_FILE", state_file),
                mock.patch("ukm.core.manager.get_providers", return_value=[]),
            ):
                mgr = KernelManager()
                entry = make_entry()
                key = mgr._state_key(entry)
                assert "mainline_ppa" in key
                assert "6.9.0" in key
                assert "amd64" in key


class TestListAll:
    def test_sorted_newest_first(self, tmp_path):
        provider = _mock_provider([make_entry("6.7.0"), make_entry("6.9.0"), make_entry("6.8.0")])
        with _mgr_ctx(tmp_path, [provider]):
            mgr = KernelManager(arch="amd64")
        result = mgr.list_all()
        assert [str(e.version) for e in result] == ["6.9.0", "6.8.0", "6.7.0"]

    def test_broken_provider_skipped(self, tmp_path):
        good = _mock_provider([make_entry("6.9.0")], provider_id="good")
        bad = _mock_provider(provider_id="bad")
        bad.fetch.side_effect = RuntimeError("network error")
        with _mgr_ctx(tmp_path, [good, bad]):
            mgr = KernelManager(arch="amd64")
        assert len(mgr.list_all()) == 1

    def test_applies_persisted_note(self, tmp_path):
        state_file = tmp_path / "state.json"
        key = "mainline_ppa:6.9.0:generic:amd64"
        state_file.write_text(json.dumps({"notes": {key: "my note"}, "locked": {}}))
        provider = _mock_provider([make_entry("6.9.0")])
        with (
            mock.patch("ukm.core.manager._STATE_FILE", state_file),
            mock.patch("ukm.core.manager.get_providers", return_value=[provider]),
            mock.patch("ukm.core.manager.system_info", return_value=mock.MagicMock(arch="amd64")),
        ):
            mgr = KernelManager(arch="amd64")
        result = mgr.list_all()
        assert result[0].notes == "my note"

    def test_applies_persisted_lock(self, tmp_path):
        state_file = tmp_path / "state.json"
        key = "mainline_ppa:6.9.0:generic:amd64"
        state_file.write_text(json.dumps({"notes": {}, "locked": {key: True}}))
        provider = _mock_provider([make_entry("6.9.0", status=KernelStatus.INSTALLED)])
        with (
            mock.patch("ukm.core.manager._STATE_FILE", state_file),
            mock.patch("ukm.core.manager.get_providers", return_value=[provider]),
            mock.patch("ukm.core.manager.system_info", return_value=mock.MagicMock(arch="amd64")),
        ):
            mgr = KernelManager(arch="amd64")
        result = mgr.list_all()
        assert result[0].held is True
        assert result[0].status == KernelStatus.HELD

    def test_list_installed(self, tmp_path):
        entries = [
            make_entry("6.9.0", status=KernelStatus.AVAILABLE),
            make_entry("6.8.0", status=KernelStatus.INSTALLED),
            make_entry("6.7.0", status=KernelStatus.RUNNING),
        ]
        provider = _mock_provider(entries)
        with _mgr_ctx(tmp_path, [provider]):
            mgr = KernelManager(arch="amd64")
        installed = mgr.list_installed()
        assert {str(e.version) for e in installed} == {"6.8.0", "6.7.0"}

    def test_running_kernel(self, tmp_path):
        entries = [
            make_entry("6.9.0"),
            make_entry("6.8.0", status=KernelStatus.RUNNING),
        ]
        provider = _mock_provider(entries)
        with _mgr_ctx(tmp_path, [provider]):
            mgr = KernelManager(arch="amd64")
        running = mgr.running_kernel()
        assert running is not None
        assert str(running.version) == "6.8.0"

    def test_running_kernel_none(self, tmp_path):
        provider = _mock_provider([make_entry("6.9.0")])
        with _mgr_ctx(tmp_path, [provider]):
            mgr = KernelManager(arch="amd64")
        assert mgr.running_kernel() is None


class TestInstall:
    def test_delegates_to_provider(self, tmp_path):
        entry = make_entry("6.9.0")
        provider = _mock_provider([entry])
        with _mgr_ctx(tmp_path, [provider]):
            mgr = KernelManager(arch="amd64")
        with mock.patch("ukm.core.dkms.autoinstall", return_value=iter([])):
            lines = list(mgr.install(entry))
        provider.install.assert_called_once_with(entry)
        assert any("installing" in line for line in lines)

    def test_raises_when_provider_missing(self, tmp_path):
        with _mgr_ctx(tmp_path):
            mgr = KernelManager(arch="amd64")
        with pytest.raises(RuntimeError, match="not found"):
            list(mgr.install(make_entry(provider_id="unknown")))

    def test_raises_when_provider_unavailable(self, tmp_path):
        entry = make_entry("6.9.0")
        provider = _mock_provider([entry], available=False)
        with _mgr_ctx(tmp_path, [provider]):
            mgr = KernelManager(arch="amd64")
        with pytest.raises(RuntimeError, match="not available"):
            list(mgr.install(entry))


class TestHoldUnhold:
    def test_hold_sets_locked(self, tmp_path):
        entry = make_entry("6.9.0")
        provider = _mock_provider([entry])
        with _mgr_ctx(tmp_path, [provider]):
            mgr = KernelManager(arch="amd64")
        with mock.patch("ukm.core.manager._STATE_FILE", tmp_path / "state.json"):
            rc, _, _ = mgr.hold(entry)
        assert rc == 0
        assert mgr._state["locked"].get("mainline_ppa:6.9.0:generic:amd64") is True

    def test_unhold_clears_locked(self, tmp_path):
        entry = make_entry("6.9.0", held=True)
        provider = _mock_provider([entry])
        with _mgr_ctx(tmp_path, [provider]):
            mgr = KernelManager(arch="amd64")
        key = "mainline_ppa:6.9.0:generic:amd64"
        mgr._state = {"notes": {}, "locked": {key: True}}
        with mock.patch("ukm.core.manager._STATE_FILE", tmp_path / "state.json"):
            rc, _, _ = mgr.unhold(entry)
        assert rc == 0
        assert mgr._state["locked"].get(key) is False

    def test_hold_missing_provider(self, tmp_path):
        with _mgr_ctx(tmp_path):
            mgr = KernelManager(arch="amd64")
        rc, _, err = mgr.hold(make_entry(provider_id="unknown"))
        assert rc == 1
        assert "not found" in err


class TestRemoveOld:
    def test_removes_old_kernels(self, tmp_path):
        entries = [
            make_entry("6.9.0", status=KernelStatus.INSTALLED),
            make_entry("6.8.0", status=KernelStatus.INSTALLED),
            make_entry("6.7.0", status=KernelStatus.INSTALLED),
            make_entry("6.6.0", status=KernelStatus.RUNNING),
        ]
        provider = _mock_provider(entries)
        with _mgr_ctx(tmp_path, [provider]):
            mgr = KernelManager(arch="amd64")
        with mock.patch("ukm.core.dkms.remove_kernel", return_value=iter([])):
            list(mgr.remove_old(keep=1))
        assert provider.remove.call_count == 2

    def test_no_old_kernels_message(self, tmp_path):
        provider = _mock_provider([make_entry("6.9.0", status=KernelStatus.RUNNING)])
        with _mgr_ctx(tmp_path, [provider]):
            mgr = KernelManager(arch="amd64")
        lines = list(mgr.remove_old(keep=1))
        assert any("no old" in line.lower() for line in lines)

    def test_held_kernels_preserved(self, tmp_path):
        entries = [
            make_entry("6.9.0", status=KernelStatus.INSTALLED, held=True),
            make_entry("6.8.0", status=KernelStatus.INSTALLED),
            make_entry("6.7.0", status=KernelStatus.RUNNING),
        ]
        provider = _mock_provider(entries)
        with _mgr_ctx(tmp_path, [provider]):
            mgr = KernelManager(arch="amd64")
        with mock.patch("ukm.core.dkms.remove_kernel", return_value=iter([])):
            list(mgr.remove_old(keep=0))
        # Only 6.8.0 should be removed; 6.9.0 is held, 6.7.0 is running
        assert provider.remove.call_count == 1
