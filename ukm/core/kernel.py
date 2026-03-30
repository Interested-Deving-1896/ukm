"""
Core data model for a kernel entry.

KernelEntry is the single shared representation used by all providers,
backends, the CLI, and the GUI. Providers produce KernelEntry objects;
the rest of the application consumes them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import total_ordering


class KernelStatus(Enum):
    AVAILABLE = auto()  # known but not installed
    INSTALLED = auto()  # installed, not running
    RUNNING = auto()  # currently running
    HELD = auto()  # installed + held/pinned (won't be auto-upgraded/removed)


class KernelFamily(Enum):
    MAINLINE = "mainline"  # Ubuntu Mainline PPA
    XANMOD = "xanmod"  # XanMod performance kernels
    LIQUORIX = "liquorix"  # Liquorix low-latency kernels
    DISTRO = "distro"  # Distribution-native kernel packages
    GENTOO = "gentoo"  # Gentoo portage / source-compiled
    LOCAL = "local"  # Locally supplied .deb/.rpm/.pkg.tar.zst
    CUSTOM = "custom"  # User-defined provider


@total_ordering
@dataclass
class KernelVersion:
    """
    Parses and compares kernel version strings of the form:
        6.9.0, 6.9.0-rc3, 6.9.0-061900-generic, 6.9.0-xanmod1, etc.

    Ordering: release > rc > pre  (e.g. 6.9.0 > 6.9.0-rc3 > 6.9.0-rc1)
    """

    raw: str
    major: int = field(init=False)
    minor: int = field(init=False)
    patch: int = field(init=False)
    pre: str | None = field(init=False)  # "rc3", "pre1", None
    suffix: str = field(init=False)  # everything after the numeric part

    _RC_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:-(rc\d+|pre\d+))?(.*)$", re.I)

    def __post_init__(self) -> None:
        m = self._RC_RE.match(self.raw.strip())
        if not m:
            # Unparseable — treat as 0.0.0 so it sorts to the bottom
            self.major, self.minor, self.patch = 0, 0, 0
            self.pre = None
            self.suffix = self.raw
            return
        self.major = int(m.group(1))
        self.minor = int(m.group(2))
        self.patch = int(m.group(3) or 0)
        self.pre = m.group(4).lower() if m.group(4) else None
        self.suffix = m.group(5) or ""

    def _pre_key(self) -> tuple[int, int]:
        """Returns a sortable key for the pre-release tag. No pre = highest."""
        if self.pre is None:
            return (2, 0)  # release > rc > pre
        m = re.match(r"(rc|pre)(\d+)", self.pre)
        if m:
            tag_order = 0 if m.group(1) == "pre" else 1  # pre < rc < release
            return (tag_order, int(m.group(2)))
        return (0, 0)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, KernelVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch, self._pre_key()) == (
            other.major,
            other.minor,
            other.patch,
            other._pre_key(),
        )

    def __lt__(self, other: KernelVersion) -> bool:
        if not isinstance(other, KernelVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch, self._pre_key()) < (
            other.major,
            other.minor,
            other.patch,
            other._pre_key(),
        )

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.pre))

    def __str__(self) -> str:
        return self.raw


@dataclass
class KernelEntry:
    """
    Represents a single installable/installed kernel.

    Produced by KernelProvider.list() and consumed everywhere else.
    """

    # Identity
    version: KernelVersion
    family: KernelFamily
    provider_id: str  # e.g. "mainline_ppa", "xanmod", "apt"
    arch: str  # e.g. "amd64", "arm64", "x86_64"

    # Display
    flavor: str = ""  # e.g. "generic", "lowlatency", "rt", "v3"
    description: str = ""

    # State
    status: KernelStatus = KernelStatus.AVAILABLE
    held: bool = False

    # Metadata
    size_bytes: int | None = None
    checksum: str | None = None  # sha256 hex
    source_url: str | None = None
    notes: str = ""

    @property
    def display_name(self) -> str:
        parts = [str(self.version)]
        if self.flavor:
            parts.append(self.flavor)
        return "-".join(parts)

    @property
    def is_installed(self) -> bool:
        return self.status in (KernelStatus.INSTALLED, KernelStatus.RUNNING, KernelStatus.HELD)

    @property
    def is_running(self) -> bool:
        return self.status == KernelStatus.RUNNING

    def __repr__(self) -> str:
        return (
            f"KernelEntry({self.display_name!r}, family={self.family.value}, "
            f"arch={self.arch!r}, status={self.status.name})"
        )
