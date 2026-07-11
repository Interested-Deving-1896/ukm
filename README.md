[update-readmes]   Mode: rewrite — migrating to template structure...
# ukm

[![Built with Ona](https://ona.com/build-with-ona.svg)](https://app.ona.com/#https://github.com/Interested-Deving-1896/ukm) [![KDE Eco](https://img.shields.io/badge/KDE%20Eco-certified-brightgreen?logo=kde&logoColor=white&style=flat-square)](https://eco.kde.org/) [![Blue Angel](https://img.shields.io/badge/Blue%20Angel-DE--UZ%20215-0055a4?style=flat-square)](https://www.blauer-engel.de/en/certification/criteria) [![Energy](https://api.green-coding.io/v1/ci/badge/get?repo=Interested-Deving-1896%2Fukm&branch=main&workflow=eco-audit.yml)](https://metrics.green-coding.io/ci-index.html)


<!-- AI:start:what-it-does -->
_Description pending._
<!-- AI:end:what-it-does -->

## Architecture

<!-- AI:start:architecture -->
The project consists of two main components: a command-line interface (CLI) and an optional graphical user interface (GUI). The CLI handles kernel management tasks such as installation, removal, and listing available kernels. The GUI provides a Qt-based interface, supporting both PySide6 and PyQt6. The core logic is shared between the CLI and GUI, ensuring consistent functionality. The project uses `docopt` for CLI argument parsing and optional dependencies for GUI support.

The directory structure is as follows:

```plaintext
.
├── .github/               # GitHub workflows and CI configurations
├── debian/                # Debian packaging files
├── scripts/               # Auxiliary scripts for packaging and deployment
├── share/                 # Shared resources (e.g., icons, desktop files)
├── tests/                 # Unit and integration tests
├── ukm/                   # Core application code
│   ├── cli/               # CLI implementation
│   ├── gui/               # GUI implementation
│   ├── kernel/            # Kernel management logic
│   └── utils/             # Utility functions and helpers
├── CHANGELOG.md           # Project changelog
├── CONTRIBUTING.md        # Contribution guidelines
├── LICENSE                # License file
├── README.md              # Project documentation
├── pyproject.toml         # Build system and dependency configuration
└── uv.lock                # Lockfile for dependency resolution
```
<!-- AI:end:architecture -->

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

## Usage

<!-- Add usage examples here. This section is yours — the AI will not modify it. -->

## Configuration

<!-- Document configuration options here. This section is yours — the AI will not modify it. -->

## CI

<!-- AI:start:ci -->
The repository uses GitHub Actions for continuous integration and automation. Below are the workflows and their purposes:

- **integration.yml**: Runs tests, linting (Ruff), type checks (Mypy), and coverage analysis (pytest-cov) on supported Python versions. No secrets required.
- **mirror-osp-to-ooc.yaml**: Mirrors the repository from the "open-source project" (OSP) namespace to the "organization-owned copy" (OOC). Requires `GITHUB_TOKEN`.
- **ppa-upload.yml**: Builds and uploads `.deb` packages to a PPA. Requires `PPA_SIGNING_KEY` and `PPA_SIGNING_KEY_PASSWORD` secrets.
- **rebase-prs.yml**: Automatically rebases pull requests when updates are pushed to the target branch. Requires `GITHUB_TOKEN`.
- **trigger-artifact-mirror.yml**: Triggers artifact mirroring to external storage. Requires `ARTIFACT_STORAGE_KEY`.

Ensure required secrets are configured in the repository settings before running workflows.
<!-- AI:end:ci -->

## Mirror chain

<!-- AI:start:mirror-chain -->
This repo is maintained in [`Interested-Deving-1896/ukm`](https://github.com/Interested-Deving-1896/ukm) and mirrored through:

```
Interested-Deving-1896/ukm  ──►  OpenOS-Project-OSP/ukm  ──►  OpenOS-Project-Ecosystem-OOC/ukm
```

Changes flow downstream automatically via the hourly mirror chain in
[`fork-sync-all`](https://github.com/Interested-Deving-1896/fork-sync-all).
Direct commits to OSP or OOC are detected and opened as PRs back to `Interested-Deving-1896`.
<!-- AI:end:mirror-chain -->

## Contributors

<!-- AI:start:contributors -->
_Contributors pending._
<!-- AI:end:contributors -->

## Origins

<!-- AI:start:origins -->
_Original project — no upstream fork._
<!-- AI:end:origins -->

## Resources

<!-- AI:start:resources -->
_No additional resource files found._
<!-- AI:end:resources -->

<!-- AI:start:accessibility -->
This repo uses automated accessibility auditing via `check-accessibility.yml`.

Checks include: CODEOWNERS ownership coverage, README screen-reader compatibility,
WCAG 2.1 AA HTML compliance, audio overview (espeak-ng), and Braille output (liblouis).




Run the [Check Accessibility](https://github.com/Interested-Deving-1896/ukm/actions/workflows/check-accessibility.yml)
workflow to generate the first report and accessibility artifacts.
See [DOCS/accessibility.md](https://github.com/Interested-Deving-1896/ukm/blob/main/DOCS/accessibility.md) for the full reference.
<!-- AI:end:accessibility -->

## License

<!-- AI:start:license -->
<!-- License not detected — add a LICENSE file to this repo. -->
<!-- AI:end:license -->
