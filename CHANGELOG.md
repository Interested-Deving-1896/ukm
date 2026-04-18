# Changelog

All notable changes to ukm are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

---

## [0.1.1] — 2026-03-30

### Added
- `ukm update` — install the newest available kernel; supports `--provider`, `--flavor`, `--dry-run`, `--yes`
- `ukm remove-old --dry-run` — preview what would be removed without making changes
- `KernelManager.latest()` and `remove_old_candidates()` methods
- GUI: `Ctrl+F` shortcut and native clear button on the kernel filter bar
- GUI: "⚡ Providers" toolbar button showing per-provider status and errors
- `CHANGELOG.md`
- GitHub Release page for v0.1.0

### Fixed
- `ukm changelog` for non-Ubuntu distros: now dispatches to apt (Ubuntu+Debian),
  dnf (Fedora/Bodhi), pacman (AUR), zypper (openSUSE OBS), apk (Alpine);
  returns a useful fallback URL instead of empty string on network failure
- Provider errors no longer silently swallowed — exposed via `KernelManager.provider_errors`
  and shown in the GUI status bar

### Tests
- Portage backend: 24% → 99% coverage (42 new tests)
- Overall: 80% → 83% coverage, 521 tests (up from 437)

---

## [0.1.0] — 2026-03-30

Initial release.

### Added

#### Core
- `KernelManager` — central coordinator aggregating all providers; persists notes
  and hold state to `~/.config/ukm/state.json`
- `KernelProvider` ABC with `fetch()`, `install()`, `remove()`, `hold()`, `unhold()`
- `KernelEntry` / `KernelVersion` data model with correct rc/pre ordering
- Provider implementations: Ubuntu Mainline PPA, XanMod, Liquorix, distro-native
  (apt/pacman/dnf/zypper/apk), AUR, Gentoo, local file
- Package manager backends: apt/dpkg, pacman, dnf, zypper, apk, portage
- CPU detection (`ukm cpu`) with XanMod v1–v4 level recommendation
- DKMS integration — auto-rebuild modules after install/remove
- Desktop notification support (`ukm notify`) via `notify-send`
- Systemd user timer for background notifications (`ukm notify-enable`)
- Login-time shell snippet for non-systemd users (`ukm notify-shell-install`)
- Changelog fetcher for all providers with local cache

#### CLI (`ukm`)
- `list` — all kernels with family/installed/json/refresh filters
- `search <pattern>` — case-insensitive substring search across version, flavor, family, provider
- `install` / `remove` / `hold` / `unhold` / `note`
- `remove-old [--keep=N] [--purge]`
- `providers` / `info` / `cpu` / `dkms`
- `changelog <version>`
- `notify` / `notify-enable` / `notify-disable`
- `notify-shell-install [--shell=bash|zsh|path]` / `notify-shell-uninstall`
- `gentoo compile` / `gentoo configure` / `gentoo sources`

#### GUI
- Qt6 application (PySide6 or PyQt6) via `ukm-gui` entry point
- Tabbed kernel view (All + per-family tabs) with sortable columns
- Text filter bar + family/status dropdowns on every tab
- Right-click context menu: install, remove, hold, unhold, note, changelog
- Live streaming log panel (collapsible)
- `ProgressPanel` — indeterminate progress bar with phase labels
  (Downloading, Verifying, Installing, Rebuilding DKMS, etc.)
- XanMod CPU-level pre-selection based on `ukm cpu` detection
- Secure Boot warning in status bar

#### CI / packaging
- GitHub Actions CI: lint (ruff), type check (mypy), tests (Python 3.11 + 3.12)
- Integration CI: Ubuntu 24.04 (apt), Arch (pacman), Fedora 40 (dnf), Alpine (apk)
- PPA upload workflow (dpkg-buildpackage + dput) triggered on `v*` tags
- Debian source package (`debian/`)
- AUR PKGBUILD + `.SRCINFO`
- 437 unit tests, 80% coverage

[Unreleased]: https://gitlab.com/OSPF1896/ukm/compare/v0.1.0...HEAD
[0.1.0]: https://gitlab.com/OSPF1896/ukm/releases/tag/v0.1.0
