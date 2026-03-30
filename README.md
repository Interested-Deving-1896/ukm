# ukm — Universal Kernel Manager

Install, remove, hold, and manage Linux kernels across all major distributions
and CPU architectures, from a single CLI or GUI.

Combines the best of [bkw777/mainline](https://github.com/bkw777/mainline) and
[XKM-Multi-Kernel-Manager](https://github.com/bobbycomet/XKM-Multi-Kernel-Manager),
extended to cover every major Linux distribution and architecture.

---

## Kernel families supported

| Family | Source | Architectures |
|---|---|---|
| **Ubuntu Mainline PPA** | kernel.ubuntu.com/mainline | amd64, arm64, armhf, ppc64el, s390x, i386 |
| **XanMod** | xanmod.org | amd64 (v1–v4, edge, lts, rt) |
| **Liquorix** | liquorix.net | amd64 |
| **Distro-native** | System package manager | All (whatever the distro ships) |
| **Gentoo** | Portage + source compilation | All |
| **Local file** | .deb / .rpm / .pkg.tar.* / .apk | All |

## Distributions supported

Any distro using one of these package managers:

| Package manager | Distros |
|---|---|
| `apt` / `dpkg` | Debian, Ubuntu, Mint, Pop!_OS, Kali, Kubuntu, Xubuntu, Lubuntu, Devuan, MX Linux, antiX, Zorin, elementary, KDE neon, SparkyLinux, BunsenLabs, Parrot, Proxmox, PikaOS, Bodhi, Lite, Emmabuntüs, Voyager, Linuxfx, Kodachi, AV Linux, wattOS, Feren, Peppermint, Q4OS, Ubuntu MATE, Ubuntu Studio, DragonOS, … |
| `pacman` | Arch, Manjaro, EndeavourOS, CachyOS, Artix, RebornOS, Archcraft, ArchBang, Mabox, Bluestar, … |
| `dnf` | Fedora, RHEL, AlmaLinux, Rocky, Nobara, Ultramarine, Bazzite, Oracle, Red Hat, … |
| `zypper` | openSUSE Leap, openSUSE Tumbleweed, SLES, Regata, … |
| `apk` | Alpine Linux |
| `portage` | Gentoo (package mode + source compilation) |

---

## Install

```bash
# GUI (PySide6 — recommended, LGPL)
pip install "ukm[pyside6]"

# GUI (PyQt6 — alternative, GPL)
pip install "ukm[pyqt6]"

# CLI only (no Qt required)
pip install ukm
```

To force a specific Qt binding at runtime:

```bash
UKM_QT=PyQt6 ukm-gui
```

---

## CLI usage

```
ukm list                          # all kernels
ukm list --family=xanmod          # filter by family
ukm list --installed              # installed only
ukm list --json                   # machine-readable output
ukm list --refresh                # force re-fetch index

ukm install 6.9.0                 # install by version
ukm install 6.9.0 --flavor=rt     # install specific flavor
ukm install 6.9.0 --provider=xanmod

ukm remove 6.8.0
ukm remove 6.8.0 --purge          # also remove config files

ukm hold   6.9.0                  # pin kernel (won't be auto-removed/upgraded)
ukm unhold 6.9.0

ukm note 6.9.0 "stable, use this" # attach a note to a kernel

ukm remove-old                    # remove all but running + most recent
ukm remove-old --keep=2           # keep 2 most recent

ukm providers                     # list available providers
ukm info                          # system info (distro, arch, running kernel)

# Gentoo source compilation
ukm gentoo sources                # list installed source trees
ukm gentoo configure /usr/src/linux-6.9.0-gentoo
ukm gentoo compile  /usr/src/linux-6.9.0-gentoo --genkernel
ukm gentoo compile  /usr/src/linux-6.9.0-gentoo --make --jobs=8
```

---

## GUI

```bash
ukm-gui
```

The GUI shows a tabbed window with one tab per kernel family plus an **All** tab
with combined filtering. Each tab has a search bar, family/status dropdowns, a
sortable kernel table, and a live log panel at the bottom.

Right-click any kernel for Install / Remove / Hold / Unhold / Edit Note.

On Gentoo, a **Compile…** toolbar button opens a compilation dialog with
source tree selection, genkernel/make toggle, job count, and live output.

---

## Architecture

```
ukm/
├── qt.py                    # PySide6/PyQt6 compatibility shim
├── core/
│   ├── kernel.py            # KernelEntry, KernelVersion, KernelFamily, KernelStatus
│   ├── system.py            # distro/arch/package-manager detection
│   ├── manager.py           # KernelManager — central coordinator, state persistence
│   ├── backends/            # Package manager backends (apt, pacman, dnf, zypper, apk, portage)
│   └── providers/           # Kernel source providers (mainline PPA, XanMod, Liquorix, ...)
├── cli/
│   ├── main.py              # CLI entry point (docopt)
│   └── output.py            # Colour output, tables, JSON mode
└── gui/
    ├── app.py               # QApplication entry point + stylesheet
    ├── kernel_model.py      # QAbstractTableModel for KernelEntry lists
    ├── main_window.py       # Main window (toolbar, tabs, log panel)
    └── widgets/
        ├── kernel_view.py           # Filterable, sortable kernel table widget
        ├── log_panel.py             # Collapsible live log panel
        ├── note_dialog.py           # Note editing dialog
        └── gentoo_compile_dialog.py # Gentoo source compilation dialog
```

Adding a new kernel source is one file: implement `KernelProvider` in
`ukm/core/providers/` and register it in `ukm/core/providers/__init__.py`.

---

## Development

```bash
git clone https://github.com/ukm-project/ukm
cd ukm
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check ukm/

# Type check
mypy ukm/

# Launch GUI
ukm-gui

# Launch CLI
ukm info
ukm list
```

---

## Notes on specific providers

**Ubuntu Mainline PPA** — packages are unsigned; they will not boot with Secure
Boot enabled. ukm warns you at startup if Secure Boot is detected.

**XanMod / Liquorix** — x86-64 only. On first use, ukm offers to add the
required apt repository and signing key automatically.

**Gentoo source mode** — `ukm gentoo configure` prints the interactive
`make menuconfig` command for you to run in a terminal (it cannot be run
inside the GUI). `ukm gentoo compile` streams the full build output live.

---

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
