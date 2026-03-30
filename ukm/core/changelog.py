"""
Kernel changelog / release notes fetcher.

Sources per provider:
  mainline_ppa    — https://kernel.ubuntu.com/mainline/vX.Y.Z/CHANGES
  distro (apt)    — /usr/share/doc/linux-image-<ver>/changelog.Debian.gz
                    → changelogs.ubuntu.com (Ubuntu)
                    → packages.debian.org  (Debian)
  distro (dnf)    — https://koji.fedoraproject.org/koji/search (Fedora/RHEL)
                    → https://bodhi.fedoraproject.org/updates (Fedora updates)
  distro (pacman) — https://archlinux.org/packages/core/x86_64/linux/
  distro (zypper) — https://software.opensuse.org/package/kernel-default
  distro (apk)    — https://pkgs.alpinelinux.org/package/edge/main/x86_64/linux-lts
  xanmod          — https://xanmod.org  (release notes page)
  liquorix        — https://liquorix.net/CHANGELOG
  aur             — AUR package git log
  gentoo          — https://gitweb.gentoo.org/repo/gentoo.git/log/sys-kernel/

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
    Fetch the changelog for a distro-native kernel.

    Strategy:
    1. Read the local compressed changelog from /usr/share/doc (all distros).
    2. Dispatch to a distro-specific online source based on which package
       manager is present.
    """
    import shutil

    # ------------------------------------------------------------------
    # 1. Local changelog (works on any distro that installs doc packages)
    # ------------------------------------------------------------------
    flavor_str = flavor or "generic"

    # apt/dpkg layout: /usr/share/doc/linux-image-<ver>-<flavor>/
    for doc_dir in (
        Path(f"/usr/share/doc/linux-image-{version}-{flavor_str}"),
        Path(f"/usr/share/doc/linux-image-{version}"),
    ):
        for name in ("changelog.Debian.gz", "changelog.gz", "NEWS.Debian.gz"):
            f = doc_dir / name
            if f.exists():
                try:
                    return gzip.decompress(f.read_bytes()).decode("utf-8", errors="replace")
                except Exception:
                    pass

    # rpm layout: /usr/share/doc/kernel-<ver>/
    for doc_dir in (
        Path(f"/usr/share/doc/kernel-{version}"),
        Path(f"/usr/share/doc/kernel-core-{version}"),
    ):
        for name in ("ChangeLog", "changelog", "NEWS"):
            f = doc_dir / name
            if f.exists():
                try:
                    return f.read_text(errors="replace")
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 2. Online fallback — dispatch by package manager
    # ------------------------------------------------------------------

    # apt — Ubuntu or Debian
    if shutil.which("apt-get"):
        return _fetch_distro_apt(version, flavor_str)

    # dnf / yum — Fedora, RHEL, CentOS
    if shutil.which("dnf") or shutil.which("yum"):
        return _fetch_distro_dnf(version, flavor_str)

    # pacman — Arch Linux (use the AUR/official package page)
    if shutil.which("pacman"):
        pkg = flavor_str if flavor_str not in ("generic", "") else "linux"
        return _fetch_aur(version, pkg)

    # zypper — openSUSE
    if shutil.which("zypper"):
        return _fetch_distro_zypper(version, flavor_str)

    # apk — Alpine Linux
    if shutil.which("apk"):
        return _fetch_distro_apk(version, flavor_str)

    return ""


def _fetch_distro_apt(version: str, flavor: str) -> str:
    """Ubuntu changelogs.ubuntu.com → Debian tracker fallback."""
    import re

    pkg = f"linux-image-{version}-{flavor}"

    # Ubuntu
    url = f"https://changelogs.ubuntu.com/changelogs/pool/main/l/linux/{pkg}/changelog"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        pass

    # Debian — strip Ubuntu-specific suffix from version (e.g. "6.1.0-28-amd64" → "6.1.0")
    base_ver = re.sub(r"-\d+$", "", version)
    url = f"https://packages.debian.org/changelogs/pool/main/l/linux/linux_{base_ver}/changelog"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        pass

    return f"See https://packages.debian.org/search?keywords=linux-image-{version}"


def _fetch_distro_dnf(version: str, flavor: str) -> str:
    """Fedora Bodhi updates page for the kernel package."""
    import re

    # Strip distro suffix: "6.9.0-100.fc40.x86_64" → "6.9.0"
    base_ver = re.sub(r"[-.]fc\d+.*$", "", version)
    base_ver = re.sub(r"[-.]el\d+.*$", "", base_ver)

    # Try Bodhi (Fedora updates tracker)
    url = f"https://bodhi.fedoraproject.org/updates/?packages=kernel&search={base_ver}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            html = r.read().decode("utf-8", errors="replace")
        msgs = re.findall(r'"notes"\s*:\s*"([^"]{20,})"', html)
        if msgs:
            return "\n\n".join(msgs[:5])
    except Exception:
        pass

    # Fallback: Koji build search
    return (
        f"See https://bodhi.fedoraproject.org/updates/?packages=kernel&search={base_ver}\n"
        f"Or: https://koji.fedoraproject.org/koji/search?terms=kernel-{base_ver}&type=build"
    )


def _fetch_distro_zypper(version: str, flavor: str) -> str:
    """openSUSE OBS changelog page."""
    import re

    pkg = f"kernel-{flavor}" if flavor not in ("generic", "") else "kernel-default"

    url = f"https://software.opensuse.org/package/{pkg}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            html = r.read().decode("utf-8", errors="replace")
        # Extract changelog entries
        msgs = re.findall(r"<li[^>]*>\s*<strong[^>]*>([^<]+)</strong>\s*<[^>]+>([^<]+)", html)
        if msgs:
            return "\n".join(f"• {date}: {msg}" for date, msg in msgs[:20])
    except Exception:
        pass

    return f"See https://software.opensuse.org/package/{pkg}"


def _fetch_distro_apk(version: str, flavor: str) -> str:
    """Alpine Linux aports changelog via pkgs.alpinelinux.org."""
    import re

    pkg = f"linux-{flavor}" if flavor not in ("generic", "") else "linux-lts"

    url = f"https://pkgs.alpinelinux.org/package/edge/main/x86_64/{pkg}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            html = r.read().decode("utf-8", errors="replace")
        # Extract version history table
        rows = re.findall(r"<tr[^>]*>.*?</tr>", html, re.DOTALL)
        entries = []
        for row in rows[:10]:
            cells = re.findall(r"<td[^>]*>([^<]+)</td>", row)
            if len(cells) >= 2:
                entries.append(" — ".join(c.strip() for c in cells[:3]))
        if entries:
            return "\n".join(entries)
    except Exception:
        pass

    return f"See https://pkgs.alpinelinux.org/package/edge/main/x86_64/{pkg}"


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
