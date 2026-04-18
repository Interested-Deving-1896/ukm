# Contributing to ukm

## Development setup

```bash
git clone https://gitlab.com/OSPF1896/ukm
cd ukm
pip install -e ".[dev]"
```

## Running tests

```bash
pytest
```

## Adding a kernel provider

1. Create `ukm/core/providers/<name>.py` implementing `KernelProvider`
2. Register it in `ukm/core/providers/__init__.py` inside `get_providers()`
3. Add tests in `tests/`

Required methods: `id`, `display_name`, `family`, `supported_arches`,
`is_available`, `list`, `install`, `remove`.

## Adding a package backend

1. Create `ukm/core/backends/<name>.py` implementing `PackageBackend`
2. Register it in `ukm/core/backends/__init__.py` in `_BACKEND_MAP`

## Qt binding

All GUI code imports from `ukm.qt`, never directly from PySide6 or PyQt6.
Set `UKM_QT=PyQt6` to test against PyQt6.

## Code style

```bash
ruff check ukm/
ruff format ukm/
mypy ukm/
```
