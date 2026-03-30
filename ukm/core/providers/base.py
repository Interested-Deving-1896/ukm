"""
Abstract base class for kernel providers.

A KernelProvider knows about one family of kernels (e.g. Ubuntu Mainline PPA,
XanMod, distro-native). It produces KernelEntry objects and delegates actual
package operations to a PackageBackend.

Providers are architecture-aware: supported_arches() declares what they can
deliver. The UI and CLI filter providers by the current system architecture.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from ukm.core.kernel import KernelEntry, KernelFamily


class KernelProvider(ABC):
    def __init__(self, backend) -> None:
        # backend: PackageBackend — injected so providers are testable
        self._backend = backend

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def id(self) -> str:
        """Stable machine identifier, e.g. 'mainline_ppa'."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the GUI tab, e.g. 'Ubuntu Mainline PPA'."""

    @property
    @abstractmethod
    def family(self) -> KernelFamily:
        """The KernelFamily this provider belongs to."""

    @property
    @abstractmethod
    def supported_arches(self) -> list[str]:
        """
        List of normalised arch strings this provider can serve.
        Use ['*'] to mean all architectures.
        """

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return True if this provider can operate on the current system.
        Checks for required tools, repos, network access, etc.
        """

    def availability_reason(self) -> str:
        """
        Human-readable explanation of why is_available() returned False.
        Override to give actionable messages.
        """
        return ""

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    @abstractmethod
    def list(self, arch: str, refresh: bool = False) -> list[KernelEntry]:
        """
        Return all known kernels for the given arch.
        refresh=True forces a cache/index refresh before listing.
        """

    @abstractmethod
    def install(self, entry: KernelEntry) -> Iterator[str]:
        """
        Install the given kernel. Yields log lines as they are produced.
        Raises RuntimeError on fatal errors.
        """

    @abstractmethod
    def remove(self, entry: KernelEntry, purge: bool = False) -> Iterator[str]:
        """
        Remove the given kernel. Yields log lines.
        """

    def hold(self, entry: KernelEntry) -> tuple[int, str, str]:
        """Hold/pin the kernel. Default delegates to the backend."""
        return self._backend.hold([entry.display_name])

    def unhold(self, entry: KernelEntry) -> tuple[int, str, str]:
        """Release a held kernel."""
        return self._backend.unhold([entry.display_name])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def supports_arch(self, arch: str) -> bool:
        arches = self.supported_arches
        return "*" in arches or arch in arches

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id!r})"
