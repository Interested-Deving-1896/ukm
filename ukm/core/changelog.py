"""
Kernel changelog / release notes fetcher.

Sources per provider:
  mainline_ppa  — https://kernel.ubuntu.com/mainline/vX.Y.Z/CHANGES
  distro (apt)  — /usr/share/doc/linux-image-<ver>/changelog.Debian.gz
  distro (dnf)  — `dnf changelog kernel-<ver>` (dnf-plugins-core)
  distro (pacman) — https://archlinux.org/packages/core/x86_64/linux/
  xanmod        — https://xanmod.org  (release notes page)
  liquorix      — https://liquorix.net/CHANGELOG
  aur           — AUR package page comments / git log
  gentoo        — https://gitweb.gentoo.org/repo/gentoo.git/log/sys-kernel/

Results are cached in ~/.cache/ukm/changelogs/<provider>/<version>.txt
"""

from __future__ import annotations

import gzip
import urllib.request
from pathlib import Path

_CACHE_DIR = Path.home() / ".cache" / "ukm" / "changelogs"
_TIMEOUT = 10


def fetch(provider_id: str, version: str, flavor: str = "") -> str:
    """
    Return the changelog text for a kernel entry.
    Returns a cached copy if available. Returns '' if unavailable.
    """
    cache_key = f"{provider_id}/{version}{('-' + flavor) if flavor else ''}.txt"
    cache_file = _CACHE_DIR / cache_key
    if cache_file.exists():
        return cache_file.read_text(errors="replace")

    text = _fetch_remote(provider_id, version, flavor)
    if text:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, errors="replace")
    return text


def _fetch_remote(provider_id: str, version: str, flavor: str) -> str:
    fetchers = {
        "mainline_ppa": _fetch_mainline,
        "xanmod": _fetch_xanmod,
        "liquorix": _fetch_liquorix,
        "distro_native": _fetch_distro_native,
        "aur": _fetch_aur,
        "gentoo": _fetch_gentoo,
    }
    fn = fetchers.get(provider_id)
    if fn is None:
        return ""
    try:
        return fn(version, flavor) or ""
    except Exception as e:
        return f"(Could not fetch changelog: {e})"


# ---------------------------------------------------------------------------
# Per-provider fetchers
# ---------------------------------------------------------------------------


def _fetch_mainline(version: str, flavor: str) -> str:
    """Fetch CHANGES file from the Ubuntu Mainline PPA."""
    base = f"https://kernel.ubuntu.com/mainline/v{version}/"
    for name in ("CHANGES", "ChangeLog", "changelog"):
        url = base + name
        try:
            with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception:
            continue
    return ""


def _fetch_xanmod(version: str, flavor: str) -> str:
    """Fetch XanMod release notes from xanmod.org."""
    url = "https://xanmod.org"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            html = r.read().decode("utf-8", errors="replace")
        # Extract the section relevant to this version
        import re

        # Find paragraphs mentioning the version
        matches = re.findall(
            rf"(?:^|\n)([^\n]*{re.escape(version)}[^\n]*(?:\n(?!^[A-Z]).*)*)", html, re.MULTILINE
        )
        if matches:
            return "\n".join(matches[:10])
        return f"See https://xanmod.org for XanMod {version} release notes."
    except Exception:
        return ""


def _fetch_liquorix(version: str, flavor: str) -> str:
    """Fetch Liquorix CHANGELOG."""
    url = "https://liquorix.net/CHANGELOG"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            text = r.read().decode("utf-8", errors="replace")
        # Extract section for this version
        lines = text.splitlines()
        in_section = False
        result: list[str] = []
        for line in lines:
            if version in line:
                in_section = True
            elif in_section and line.startswith("---"):
                break
            if in_section:
                result.append(line)
        return "\n".join(result) if result else text[:3000]
    except Exception:
        return ""


def _fetch_distro_native(version: str, flavor: str) -> str:
    """
    Try to read the installed changelog from /usr/share/doc.
    Falls back to an online lookup for apt-based systems.
    """
    import shutil

    # Try local compressed changelog first
    flavor_str = flavor or "generic"
    doc_path = Path(f"/usr/share/doc/linux-image-{version}-{flavor_str}")
    for name in ("changelog.Debian.gz", "changelog.gz", "NEWS.Debian.gz"):
        f = doc_path / name
        if f.exists():
            try:
                return gzip.decompress(f.read_bytes()).decode("utf-8", errors="replace")
            except Exception:
                pass

    # Try Ubuntu package changelog API
    if shutil.which("apt-get"):
        pkg = f"linux-image-{version}-{flavor_str}"
        url = f"https://changelogs.ubuntu.com/changelogs/pool/main/l/linux/{pkg}/changelog"
        try:
            with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception:
            pass

    return ""


def _fetch_aur(version: str, flavor: str) -> str:
    """Fetch AUR package git log summary."""
    pkg = flavor or f"linux-{version}"
    url = f"https://aur.archlinux.org/cgit/aur.git/log/?h={pkg}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            html = r.read().decode("utf-8", errors="replace")
        import re

        # Extract commit messages from cgit HTML
        msgs = re.findall(r"<td class=\'subject\'><a[^>]+>([^<]+)</a>", html)
        if msgs:
            return "\n".join(f"• {m}" for m in msgs[:20])
        return f"See https://aur.archlinux.org/packages/{pkg} for details."
    except Exception:
        return ""


def _fetch_gentoo(version: str, flavor: str) -> str:
    """Fetch Gentoo kernel package commit log from gitweb."""
    pkg = flavor or "gentoo-sources"
    url = f"https://gitweb.gentoo.org/repo/gentoo.git/log/sys-kernel/{pkg}?qt=grep&q={version}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            html = r.read().decode("utf-8", errors="replace")
        import re

        msgs = re.findall(r'<td class="subject"><a[^>]+>([^<]+)</a>', html)
        if msgs:
            return "\n".join(f"• {m}" for m in msgs[:20])
        return f"See https://packages.gentoo.org/packages/sys-kernel/{pkg}"
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def clear_cache(provider_id: str | None = None) -> int:
    """Clear cached changelogs. Returns number of files removed."""
    target = _CACHE_DIR / provider_id if provider_id else _CACHE_DIR
    if not target.exists():
        return 0
    files = list(target.rglob("*.txt"))
    for f in files:
        f.unlink()
    return len(files)
