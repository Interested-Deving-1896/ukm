"""
Kernel providers registry.

get_providers() returns all providers that are compatible with the current
system architecture. Providers that require a specific package manager or
architecture are automatically filtered out.
"""

from __future__ import annotations

from ukm.core.backends import get_backend
from ukm.core.backends.portage import PortageBackend
from ukm.core.providers.base import KernelProvider
from ukm.core.providers.mainline_ppa import MainlinePPAProvider
from ukm.core.providers.xanmod import XanModProvider
from ukm.core.providers.liquorix import LiquorixProvider
from ukm.core.providers.distro_native import DistroNativeProvider
from ukm.core.providers.gentoo import GentooProvider
from ukm.core.providers.local_file import LocalFileProvider
from ukm.core.system import system_info


def get_providers(arch: str | None = None) -> list[KernelProvider]:
    """
    Return all providers compatible with the current system.

    arch defaults to the detected system architecture.
    Providers that don't support the arch are excluded.
    Providers that require unavailable tools are included but marked
    unavailable (so the GUI can show them greyed out with a reason).
    """
    target_arch = arch or system_info().arch
    backend = get_backend()

    # Build the full provider list
    all_providers: list[KernelProvider] = [
        MainlinePPAProvider(backend),
        XanModProvider(backend),
        LiquorixProvider(backend),
        DistroNativeProvider(backend),
        LocalFileProvider(backend),
    ]

    # Add Gentoo provider only when portage is the backend
    if isinstance(backend, PortageBackend):
        all_providers.append(GentooProvider(backend))

    # Filter by architecture support
    return [p for p in all_providers if p.supports_arch(target_arch)]


__all__ = [
    "KernelProvider",
    "MainlinePPAProvider",
    "XanModProvider",
    "LiquorixProvider",
    "DistroNativeProvider",
    "GentooProvider",
    "LocalFileProvider",
    "get_providers",
]
