"""
CPU capability detection for XanMod ISA-level flavor selection.

XanMod publishes four x86-64 ISA-level builds:
  v1 — baseline x86-64 (any CPU)
  v2 — x86-64-v2: CMPXCHG16B, LAHF-SAHF, POPCNT, SSE3, SSE4.1, SSE4.2, SSSE3
  v3 — x86-64-v3: v2 + AVX, AVX2, BMI1, BMI2, F16C, FMA, LZCNT, MOVBE, XSAVE
  v4 — x86-64-v4: v3 + AVX-512 (EVEX subset)

Detection reads /proc/cpuinfo flags and maps them to the highest compatible level.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


# Flags required for each ISA level (must ALL be present)
_V2_FLAGS = {"cx16", "lahf_lm", "popcnt", "sse4_1", "sse4_2", "ssse3"}
_V3_FLAGS = {"avx", "avx2", "bmi1", "bmi2", "f16c", "fma", "abm", "movbe", "xsave"}
_V4_FLAGS = {"avx512f", "avx512bw", "avx512cd", "avx512dq", "avx512vl"}


@lru_cache(maxsize=1)
def cpu_flags() -> frozenset[str]:
    """Return the set of CPU feature flags from /proc/cpuinfo."""
    try:
        text = Path("/proc/cpuinfo").read_text()
        for line in text.splitlines():
            if line.startswith("flags"):
                _, _, flags_str = line.partition(":")
                return frozenset(flags_str.strip().split())
    except FileNotFoundError:
        pass
    return frozenset()


def recommended_xanmod_level() -> str:
    """
    Return the highest XanMod ISA level supported by the current CPU.
    Returns one of: 'v4', 'v3', 'v2', 'v1'.
    """
    flags = cpu_flags()
    if _V4_FLAGS.issubset(flags):
        return "v4"
    if _V3_FLAGS.issubset(flags):
        return "v3"
    if _V2_FLAGS.issubset(flags):
        return "v2"
    return "v1"


def xanmod_level_description(level: str) -> str:
    descriptions = {
        "v1": "Any x86-64 CPU (safe default)",
        "v2": "SSE4.2+ (~2008 onwards)",
        "v3": "AVX2+ (Intel Haswell / AMD Ryzen+)",
        "v4": "AVX-512 (high-end modern CPUs only)",
    }
    return descriptions.get(level, level)


def cpu_summary() -> dict:
    """Return a human-readable summary of detected CPU capabilities."""
    flags = cpu_flags()
    level = recommended_xanmod_level()
    return {
        "recommended_xanmod_level": level,
        "description": xanmod_level_description(level),
        "has_avx512": bool(_V4_FLAGS.issubset(flags)),
        "has_avx2": bool(_V3_FLAGS.issubset(flags)),
        "has_sse4_2": bool(_V2_FLAGS.issubset(flags)),
        "flag_count": len(flags),
    }
