"""Tests for desktop notification support and cooldown logic."""

from __future__ import annotations

import json
import unittest.mock as mock
from datetime import datetime, timedelta

from ukm.core.notify import (
    _COOLDOWN_H,
    _load_notify_state,
    _save_notify_state,
    check_and_notify,
    send_notification,
)

# KernelManager is now a module-level import in notify.py, so patch there
_MGR_PATH = "ukm.core.notify.KernelManager"
_SYS_PATH = "ukm.core.notify.system_info"


# ---------------------------------------------------------------------------
# send_notification
# ---------------------------------------------------------------------------


class TestSendNotification:
    def test_returns_false_when_notify_send_missing(self):
        with mock.patch("shutil.which", return_value=None):
            assert send_notification("Test") is False

    def test_returns_true_on_success(self):
        with (
            mock.patch("shutil.which", return_value="/usr/bin/notify-send"),
            mock.patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = mock.MagicMock(returncode=0)
            assert send_notification("Test summary", body="body text") is True
            cmd = mock_run.call_args[0][0]
            assert "Test summary" in cmd
            assert "body text" in cmd

    def test_returns_false_on_nonzero_exit(self):
        with (
            mock.patch("shutil.which", return_value="/usr/bin/notify-send"),
            mock.patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = mock.MagicMock(returncode=1)
            assert send_notification("Test") is False

    def test_returns_false_on_exception(self):
        with (
            mock.patch("shutil.which", return_value="/usr/bin/notify-send"),
            mock.patch("subprocess.run", side_effect=OSError("no such file")),
        ):
            assert send_notification("Test") is False

    def test_urgency_and_timeout_in_command(self):
        with (
            mock.patch("shutil.which", return_value="/usr/bin/notify-send"),
            mock.patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = mock.MagicMock(returncode=0)
            send_notification("T", urgency="critical", timeout_ms=5000)
            cmd = mock_run.call_args[0][0]
            assert "--urgency=critical" in cmd
            assert "--expire-time=5000" in cmd


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


class TestNotifyState:
    def test_load_returns_empty_when_missing(self, tmp_path):
        with mock.patch("ukm.core.notify._STATE_FILE", tmp_path / "notify_state.json"):
            assert _load_notify_state() == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        state_file = tmp_path / "notify_state.json"
        with mock.patch("ukm.core.notify._STATE_FILE", state_file):
            _save_notify_state("6.9.0")
            state = _load_notify_state()
        assert state["last_version"] == "6.9.0"
        assert "last_notified_at" in state

    def test_save_updates_existing_state(self, tmp_path):
        state_file = tmp_path / "notify_state.json"
        with mock.patch("ukm.core.notify._STATE_FILE", state_file):
            _save_notify_state("6.8.0")
            _save_notify_state("6.9.0")
            state = _load_notify_state()
        assert state["last_version"] == "6.9.0"

    def test_load_returns_empty_on_corrupt_file(self, tmp_path):
        state_file = tmp_path / "notify_state.json"
        state_file.write_text("not valid json{{{")
        with mock.patch("ukm.core.notify._STATE_FILE", state_file):
            assert _load_notify_state() == {}


# ---------------------------------------------------------------------------
# check_and_notify — cooldown logic
# ---------------------------------------------------------------------------


def _make_entry(ver_str, provider_id="mainline_ppa", installed=False):
    from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion

    return KernelEntry(
        version=KernelVersion(ver_str),
        family=KernelFamily.MAINLINE,
        provider_id=provider_id,
        arch="amd64",
        status=KernelStatus.INSTALLED if installed else KernelStatus.AVAILABLE,
    )


def _notify_patches(tmp_path, entries, running="6.8.0", notify_send=True):
    """Return a dict of patch kwargs for check_and_notify tests."""
    return {
        _MGR_PATH: mock.MagicMock(
            return_value=mock.MagicMock(list_all=mock.MagicMock(return_value=entries))
        ),
        _SYS_PATH: mock.MagicMock(return_value=mock.MagicMock(running_kernel=running)),
        "ukm.core.notify._STATE_FILE": tmp_path / "state.json",
        "shutil.which": mock.MagicMock(
            return_value="/usr/bin/notify-send" if notify_send else None
        ),
        "subprocess.run": mock.MagicMock(return_value=mock.MagicMock(returncode=0)),
    }


class TestCheckAndNotify:
    def test_sends_when_newer_kernel_available(self, tmp_path):
        entries = [_make_entry("6.9.0"), _make_entry("6.8.0", installed=True)]
        with (
            mock.patch(_MGR_PATH) as mock_mgr_cls,
            mock.patch(_SYS_PATH, return_value=mock.MagicMock(running_kernel="6.8.0")),
            mock.patch("ukm.core.notify._STATE_FILE", tmp_path / "state.json"),
            mock.patch("shutil.which", return_value="/usr/bin/notify-send"),
            mock.patch("subprocess.run", return_value=mock.MagicMock(returncode=0)),
        ):
            mock_mgr_cls.return_value.list_all.return_value = entries
            assert check_and_notify("mainline_ppa") is True

    def test_no_notification_when_no_available_entries(self, tmp_path):
        entries = [_make_entry("6.8.0", installed=True)]
        with (
            mock.patch(_MGR_PATH) as mock_mgr_cls,
            mock.patch(_SYS_PATH, return_value=mock.MagicMock(running_kernel="6.8.0")),
            mock.patch("ukm.core.notify._STATE_FILE", tmp_path / "state.json"),
        ):
            mock_mgr_cls.return_value.list_all.return_value = entries
            assert check_and_notify("mainline_ppa") is False

    def test_no_notification_when_available_not_newer(self, tmp_path):
        entries = [_make_entry("6.7.0"), _make_entry("6.8.0", installed=True)]
        with (
            mock.patch(_MGR_PATH) as mock_mgr_cls,
            mock.patch(_SYS_PATH, return_value=mock.MagicMock(running_kernel="6.8.0")),
            mock.patch("ukm.core.notify._STATE_FILE", tmp_path / "state.json"),
        ):
            mock_mgr_cls.return_value.list_all.return_value = entries
            assert check_and_notify("mainline_ppa") is False

    def test_cooldown_suppresses_repeat_notification(self, tmp_path):
        state_file = tmp_path / "state.json"
        recent = (datetime.now() - timedelta(hours=1)).isoformat()
        state_file.write_text(json.dumps({"last_version": "6.9.0", "last_notified_at": recent}))
        entries = [_make_entry("6.9.0"), _make_entry("6.8.0", installed=True)]
        with (
            mock.patch(_MGR_PATH) as mock_mgr_cls,
            mock.patch(_SYS_PATH, return_value=mock.MagicMock(running_kernel="6.8.0")),
            mock.patch("ukm.core.notify._STATE_FILE", state_file),
        ):
            mock_mgr_cls.return_value.list_all.return_value = entries
            assert check_and_notify("mainline_ppa") is False

    def test_cooldown_allows_notification_after_expiry(self, tmp_path):
        state_file = tmp_path / "state.json"
        old = (datetime.now() - timedelta(hours=_COOLDOWN_H + 1)).isoformat()
        state_file.write_text(json.dumps({"last_version": "6.9.0", "last_notified_at": old}))
        entries = [_make_entry("6.9.0"), _make_entry("6.8.0", installed=True)]
        with (
            mock.patch(_MGR_PATH) as mock_mgr_cls,
            mock.patch(_SYS_PATH, return_value=mock.MagicMock(running_kernel="6.8.0")),
            mock.patch("ukm.core.notify._STATE_FILE", state_file),
            mock.patch("shutil.which", return_value="/usr/bin/notify-send"),
            mock.patch("subprocess.run", return_value=mock.MagicMock(returncode=0)),
        ):
            mock_mgr_cls.return_value.list_all.return_value = entries
            assert check_and_notify("mainline_ppa") is True

    def test_new_version_bypasses_cooldown(self, tmp_path):
        state_file = tmp_path / "state.json"
        recent = (datetime.now() - timedelta(hours=1)).isoformat()
        state_file.write_text(json.dumps({"last_version": "6.9.0", "last_notified_at": recent}))
        entries = [_make_entry("6.10.0"), _make_entry("6.8.0", installed=True)]
        with (
            mock.patch(_MGR_PATH) as mock_mgr_cls,
            mock.patch(_SYS_PATH, return_value=mock.MagicMock(running_kernel="6.8.0")),
            mock.patch("ukm.core.notify._STATE_FILE", state_file),
            mock.patch("shutil.which", return_value="/usr/bin/notify-send"),
            mock.patch("subprocess.run", return_value=mock.MagicMock(returncode=0)),
        ):
            mock_mgr_cls.return_value.list_all.return_value = entries
            assert check_and_notify("mainline_ppa") is True

    def test_no_notification_when_notify_send_missing(self, tmp_path):
        entries = [_make_entry("6.9.0"), _make_entry("6.8.0", installed=True)]
        with (
            mock.patch(_MGR_PATH) as mock_mgr_cls,
            mock.patch(_SYS_PATH, return_value=mock.MagicMock(running_kernel="6.8.0")),
            mock.patch("ukm.core.notify._STATE_FILE", tmp_path / "state.json"),
            mock.patch("shutil.which", return_value=None),
        ):
            mock_mgr_cls.return_value.list_all.return_value = entries
            assert check_and_notify("mainline_ppa") is False
