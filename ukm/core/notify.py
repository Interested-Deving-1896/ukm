"""
Desktop notification support.

Sends a notify-send notification when a new kernel is available.
Designed to be called from a systemd user timer or cron job via:

    ukm notify

The notifier checks the latest available kernel against the currently
running one and sends a desktop notification if a newer version exists.
It respects a cooldown so it doesn't spam the user on every timer tick.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from ukm.core.system import system_info

_STATE_FILE = Path.home() / ".config" / "ukm" / "notify_state.json"
_COOLDOWN_H = 24  # minimum hours between repeat notifications for the same version
_APP_NAME = "ukm"
_ICON = "system-software-update"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_and_notify(provider_id: str = "mainline_ppa") -> bool:
    """
    Check for a newer kernel than the one currently running and send a
    desktop notification if one is found and the cooldown has elapsed.

    Returns True if a notification was sent.
    """
    from ukm.core.kernel import KernelVersion
    from ukm.core.manager import KernelManager

    mgr = KernelManager()
    running_str = system_info().running_kernel
    running_ver = KernelVersion(running_str.split("-")[0])

    # Find the latest available (not installed) kernel from the given provider
    entries = mgr.list_all(refresh=True)
    available = [
        e for e in entries if e.provider_id == provider_id and not e.is_installed and not e.held
    ]
    if not available:
        return False

    latest = max(available, key=lambda e: e.version)

    if latest.version <= running_ver:
        return False

    # Check cooldown
    state = _load_notify_state()
    last_notified_ver = state.get("last_version", "")
    last_notified_at = state.get("last_notified_at", "")

    if last_notified_ver == str(latest.version) and last_notified_at:
        try:
            last_dt = datetime.fromisoformat(last_notified_at)
            if datetime.now() - last_dt < timedelta(hours=_COOLDOWN_H):
                return False
        except ValueError:
            pass

    # Send notification
    sent = send_notification(
        summary=f"New kernel available: {latest.version}",
        body=(
            f"Kernel {latest.version} is available from {latest.provider_id}.\n"
            f"Currently running: {running_str}\n"
            f"Run 'ukm install {latest.version}' or open ukm-gui to install."
        ),
        urgency="normal",
    )

    if sent:
        _save_notify_state(str(latest.version))

    return sent


def send_notification(
    summary: str,
    body: str = "",
    urgency: str = "normal",  # low | normal | critical
    timeout_ms: int = 10000,
) -> bool:
    """
    Send a desktop notification via notify-send.
    Returns True if the command succeeded.
    """
    if not shutil.which("notify-send"):
        return False

    cmd = [
        "notify-send",
        "--app-name",
        _APP_NAME,
        "--icon",
        _ICON,
        f"--urgency={urgency}",
        f"--expire-time={timeout_ms}",
        summary,
    ]
    if body:
        cmd.append(body)

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------


def _load_notify_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_notify_state(version: str) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = _load_notify_state()
    state["last_version"] = version
    state["last_notified_at"] = datetime.now().isoformat()
    _STATE_FILE.write_text(json.dumps(state, indent=2))
