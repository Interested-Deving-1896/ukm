"""Tests for CPU flag detection and XanMod level recommendation."""

from __future__ import annotations

import unittest.mock as mock
from ukm.core.cpu import (
    recommended_xanmod_level,
    xanmod_level_description,
    cpu_summary,
    _V2_FLAGS, _V3_FLAGS, _V4_FLAGS,
)


def _patch_flags(flags: set):
    return mock.patch("ukm.core.cpu.cpu_flags", return_value=frozenset(flags))


class TestXanModLevelDetection:

    def test_v1_no_flags(self):
        with _patch_flags(set()):
            assert recommended_xanmod_level() == "v1"

    def test_v2_with_sse4(self):
        with _patch_flags(_V2_FLAGS):
            assert recommended_xanmod_level() == "v2"

    def test_v3_with_avx2(self):
        with _patch_flags(_V2_FLAGS | _V3_FLAGS):
            assert recommended_xanmod_level() == "v3"

    def test_v4_with_avx512(self):
        with _patch_flags(_V2_FLAGS | _V3_FLAGS | _V4_FLAGS):
            assert recommended_xanmod_level() == "v4"

    def test_partial_v2_gives_v1(self):
        # Only some V2 flags — not enough
        partial = {"cx16", "popcnt"}
        with _patch_flags(partial):
            assert recommended_xanmod_level() == "v1"

    def test_partial_v3_gives_v2(self):
        # V2 complete but V3 incomplete
        partial_v3 = {"avx"}  # missing avx2, bmi1, etc.
        with _patch_flags(_V2_FLAGS | partial_v3):
            assert recommended_xanmod_level() == "v2"


class TestDescriptions:

    def test_all_levels_have_descriptions(self):
        for level in ("v1", "v2", "v3", "v4"):
            desc = xanmod_level_description(level)
            assert desc and len(desc) > 5

    def test_unknown_level_passthrough(self):
        assert xanmod_level_description("edge") == "edge"


class TestCpuSummary:

    def test_summary_keys(self):
        with _patch_flags(_V2_FLAGS | _V3_FLAGS):
            summary = cpu_summary()
        assert "recommended_xanmod_level" in summary
        assert "has_avx2" in summary
        assert "has_avx512" in summary
        assert "has_sse4_2" in summary

    def test_summary_v3_cpu(self):
        with _patch_flags(_V2_FLAGS | _V3_FLAGS):
            summary = cpu_summary()
        assert summary["recommended_xanmod_level"] == "v3"
        assert summary["has_avx2"] is True
        assert summary["has_avx512"] is False
