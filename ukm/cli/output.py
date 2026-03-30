"""
CLI output helpers — colour, tables, progress.

All output goes through these helpers so it can be silenced (--quiet),
made machine-readable (--json), or piped cleanly.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

# Detect colour support
_COLOUR = sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""

_RESET  = "\033[0m"  if _COLOUR else ""
_BOLD   = "\033[1m"  if _COLOUR else ""
_DIM    = "\033[2m"  if _COLOUR else ""
_GREEN  = "\033[32m" if _COLOUR else ""
_YELLOW = "\033[33m" if _COLOUR else ""
_CYAN   = "\033[36m" if _COLOUR else ""
_RED    = "\033[31m" if _COLOUR else ""
_BLUE   = "\033[34m" if _COLOUR else ""

_quiet = False
_json_mode = False


def set_quiet(q: bool) -> None:
    global _quiet
    _quiet = q


def set_json(j: bool) -> None:
    global _json_mode
    _json_mode = j


def info(msg: str) -> None:
    if not _quiet and not _json_mode:
        print(msg)


def log(msg: str) -> None:
    """Live streaming output (install/remove progress)."""
    if not _quiet and not _json_mode:
        print(msg, end="", flush=True)


def success(msg: str) -> None:
    if not _quiet and not _json_mode:
        print(f"{_GREEN}✓{_RESET} {msg}")


def warn(msg: str) -> None:
    if not _json_mode:
        print(f"{_YELLOW}⚠{_RESET}  {msg}", file=sys.stderr)


def error(msg: str) -> None:
    print(f"{_RED}✗{_RESET} {msg}", file=sys.stderr)


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2))


def print_table(
    rows: list[dict],
    columns: list[tuple[str, str]],  # (key, header)
    *,
    highlight_running: bool = True,
) -> None:
    """
    Print a fixed-width table.
    columns is a list of (dict_key, column_header) pairs.
    """
    if _json_mode:
        print_json(rows)
        return

    if not rows:
        info("  (none)")
        return

    # Compute column widths
    widths = {key: len(header) for key, header in columns}
    for row in rows:
        for key, _ in columns:
            widths[key] = max(widths[key], len(str(row.get(key, ""))))

    # Header
    header = "  ".join(
        f"{_BOLD}{header:<{widths[key]}}{_RESET}"
        for key, header in columns
    )
    sep = "  ".join("-" * widths[key] for key, _ in columns)
    print(header)
    print(sep)

    # Rows
    for row in rows:
        is_running = row.get("status", "") == "running"
        colour = _GREEN if is_running else (
            _CYAN if row.get("status", "") == "installed" else
            _YELLOW if row.get("held") else ""
        )
        line = "  ".join(
            f"{str(row.get(key, '')):<{widths[key]}}"
            for key, _ in columns
        )
        if colour:
            print(f"{colour}{line}{_RESET}")
        else:
            print(line)
