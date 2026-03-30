"""Tests for KernelEntry model."""

import pytest
from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus, KernelVersion


def make_entry(**kwargs) -> KernelEntry:
    defaults = dict(
        version=KernelVersion("6.9.0"),
        family=KernelFamily.MAINLINE,
        provider_id="mainline_ppa",
        arch="amd64",
        flavor="generic",
    )
    defaults.update(kwargs)
    return KernelEntry(**defaults)


class TestKernelEntry:
    def test_display_name_with_flavor(self):
        e = make_entry(flavor="lowlatency")
        assert e.display_name == "6.9.0-lowlatency"

    def test_display_name_no_flavor(self):
        e = make_entry(flavor="")
        assert e.display_name == "6.9.0"

    def test_is_installed_running(self):
        e = make_entry(status=KernelStatus.RUNNING)
        assert e.is_installed
        assert e.is_running

    def test_is_installed_held(self):
        e = make_entry(status=KernelStatus.HELD)
        assert e.is_installed
        assert not e.is_running

    def test_is_not_installed_available(self):
        e = make_entry(status=KernelStatus.AVAILABLE)
        assert not e.is_installed

    def test_repr(self):
        e = make_entry()
        assert "6.9.0" in repr(e)
        assert "mainline" in repr(e)
