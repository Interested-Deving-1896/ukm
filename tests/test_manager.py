"""Tests for KernelManager."""

from __future__ import annotations

import json
import tempfile
import unittest.mock as mock
from pathlib import Path

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion
from ukm.core.manager import KernelManager


def make_entry(version="6.9.0", status=KernelStatus.AVAILABLE, held=False, provider_id="mainline_ppa"):
    return KernelEntry(
        version=KernelVersion(version),
        family=KernelFamily.MAINLINE,
        provider_id=provider_id,
        arch="amd64",
        flavor="generic",
        status=status,
        held=held,
    )


class TestKernelManager:

    def _make_manager(self, entries=None, tmp_state=None):
        """Create a KernelManager with mocked providers and state file."""
        mgr = mock.MagicMock(spec=KernelManager)
        return mgr

    def test_notes_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with mock.patch("ukm.core.manager._STATE_FILE", state_file), \
                 mock.patch("ukm.core.manager.get_providers", return_value=[]):
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

            with mock.patch("ukm.core.manager._STATE_FILE", state_file), \
                 mock.patch("ukm.core.manager.get_providers", return_value=[]):
                mgr = KernelManager()
                entry = make_entry()
                mgr.set_note(entry, "persistent note")

            # Reload
            with mock.patch("ukm.core.manager._STATE_FILE", state_file), \
                 mock.patch("ukm.core.manager.get_providers", return_value=[]):
                mgr2 = KernelManager()
                assert mgr2.get_note(entry) == "persistent note"

    def test_remove_running_kernel_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            with mock.patch("ukm.core.manager._STATE_FILE", state_file), \
                 mock.patch("ukm.core.manager.get_providers", return_value=[]):
                mgr = KernelManager()
                entry = make_entry(status=KernelStatus.RUNNING)
                import pytest
                with pytest.raises(RuntimeError, match="running"):
                    list(mgr.remove(entry))

    def test_remove_held_kernel_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            with mock.patch("ukm.core.manager._STATE_FILE", state_file), \
                 mock.patch("ukm.core.manager.get_providers", return_value=[]):
                mgr = KernelManager()
                entry = make_entry(status=KernelStatus.INSTALLED, held=True)
                import pytest
                with pytest.raises(RuntimeError, match="locked"):
                    list(mgr.remove(entry))

    def test_secure_boot_warning_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            with mock.patch("ukm.core.manager._STATE_FILE", state_file), \
                 mock.patch("ukm.core.manager.get_providers", return_value=[]), \
                 mock.patch("ukm.core.manager.system_info") as mock_si:
                mock_si.return_value.has_secure_boot = True
                mgr = KernelManager()
                assert mgr.secure_boot_warning() is not None
                assert "Secure Boot" in mgr.secure_boot_warning()

    def test_no_secure_boot_warning_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            with mock.patch("ukm.core.manager._STATE_FILE", state_file), \
                 mock.patch("ukm.core.manager.get_providers", return_value=[]), \
                 mock.patch("ukm.core.manager.system_info") as mock_si:
                mock_si.return_value.has_secure_boot = False
                mgr = KernelManager()
                assert mgr.secure_boot_warning() is None

    def test_state_key_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            with mock.patch("ukm.core.manager._STATE_FILE", state_file), \
                 mock.patch("ukm.core.manager.get_providers", return_value=[]):
                mgr = KernelManager()
                entry = make_entry()
                key = mgr._state_key(entry)
                assert "mainline_ppa" in key
                assert "6.9.0" in key
                assert "amd64" in key
