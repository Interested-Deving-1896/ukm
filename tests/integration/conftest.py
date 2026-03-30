"""
Integration test configuration.

These tests run against real package managers and are skipped automatically
when the required tools are not present. They are designed to run inside
the CI containers defined in .github/workflows/integration.yml.
"""

from __future__ import annotations

import shutil

import pytest


def pytest_collection_modifyitems(items):
    """Skip integration tests when running outside a suitable environment."""
    for item in items:
        if "integration" in str(item.fspath):
            # Mark all integration tests so they can be selected/deselected
            item.add_marker(pytest.mark.integration)
