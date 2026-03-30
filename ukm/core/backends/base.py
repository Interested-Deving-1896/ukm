"""
Abstract base class for package manager backends.

A PackageBackend knows how to:
  - install a package (by name or local path)
  - remove a package
  - hold / unhold a package (prevent auto-upgrade)
  - query installed packages
  - run a cache refresh (apt update / pacman -Sy / etc.)

All operations that require root are expected to use privilege_escalation_cmd()
internally. Backends do NOT spawn interactive terminals; they return
(returncode, stdout, stderr) tuples so the caller (CLI or GUI) can decide
how to present output.
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from typing import Iterator


class PackageBackend(ABC):
    """Base class for all package manager backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name, e.g. 'apt', 'pacman'."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this backend's package manager is present on the system."""

    @abstractmethod
    def refresh_cache(self) -> tuple[int, str, str]:
        """
        Refresh the local package cache.
        Returns (returncode, stdout, stderr).
        """

    @abstractmethod
    def install(self, packages: list[str]) -> tuple[int, str, str]:
        """
        Install one or more packages by name.
        Returns (returncode, stdout, stderr).
        """

    @abstractmethod
    def install_local(self, paths: list[str]) -> tuple[int, str, str]:
        """
        Install one or more local package files.
        Returns (returncode, stdout, stderr).
        """

    @abstractmethod
    def remove(self, packages: list[str], purge: bool = False) -> tuple[int, str, str]:
        """
        Remove one or more packages.
        purge=True also removes config files where supported.
        Returns (returncode, stdout, stderr).
        """

    @abstractmethod
    def hold(self, packages: list[str]) -> tuple[int, str, str]:
        """Prevent packages from being auto-upgraded/removed."""

    @abstractmethod
    def unhold(self, packages: list[str]) -> tuple[int, str, str]:
        """Release a previously held package."""

    @abstractmethod
    def is_installed(self, package: str) -> bool:
        """Return True if the named package is currently installed."""

    @abstractmethod
    def is_held(self, package: str) -> bool:
        """Return True if the named package is currently held."""

    @abstractmethod
    def installed_packages(self, pattern: str = "") -> list[str]:
        """
        Return a list of installed package names matching the optional glob pattern.
        """

    # ------------------------------------------------------------------
    # Shared helper
    # ------------------------------------------------------------------

    @staticmethod
    def _run(cmd: list[str], **kwargs) -> tuple[int, str, str]:
        """Run a command and return (returncode, stdout, stderr)."""
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            **kwargs,
        )
        return result.returncode, result.stdout, result.stderr

    def stream(self, cmd: list[str], **kwargs) -> Iterator[str]:
        """
        Run a command and yield output lines as they arrive.
        Useful for the GUI log panel.
        """
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            **kwargs,
        ) as proc:
            assert proc.stdout is not None
            for line in proc.stdout:
                yield line
