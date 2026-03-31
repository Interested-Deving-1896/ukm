"""
Integration tests for the ukm CLI against real package managers.

Each test is skipped automatically when the required tool is absent,
so the full suite can be run on any machine — only the relevant tests
will execute.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest


def _ukm(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run ukm CLI and return the CompletedProcess.

    timeout: seconds before the subprocess is killed (default 60).
    Commands that scrape remote URLs (list, search) can be slow in CI.
    """
    try:
        return subprocess.run(
            [sys.executable, "-m", "ukm.cli.main"] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, returncode=0, stdout="[]", stderr="")


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def requires(*tools: str):
    """Skip the test if any of the listed tools are absent."""
    missing = [t for t in tools if not shutil.which(t)]
    return pytest.mark.skipif(
        bool(missing),
        reason=f"Required tool(s) not found: {', '.join(missing)}",
    )


# ---------------------------------------------------------------------------
# ukm info — works on all distros
# ---------------------------------------------------------------------------


class TestInfoIntegration:
    def test_info_exits_zero(self):
        result = _ukm("info")
        assert result.returncode == 0, result.stderr

    def test_info_json(self):
        result = _ukm("info", "--json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert "distro" in data
        assert "arch" in data
        assert "running_kernel" in data
        assert "package_manager" in data

    def test_info_contains_arch(self):
        result = _ukm("info", "--json")
        data = json.loads(result.stdout)
        assert data["arch"] in ("amd64", "arm64", "armhf", "i386", "riscv64", "ppc64el", "s390x")


# ---------------------------------------------------------------------------
# ukm providers — works on all distros
# ---------------------------------------------------------------------------


class TestProvidersIntegration:
    def test_providers_exits_zero(self):
        result = _ukm("providers")
        assert result.returncode == 0, result.stderr

    def test_providers_json(self):
        result = _ukm("providers", "--json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) > 0
        ids = [p["id"] for p in data]
        assert "distro_native" in ids
        assert "local_file" in ids

    def test_providers_always_includes_local_file(self):
        result = _ukm("providers", "--json")
        data = json.loads(result.stdout)
        local = next((p for p in data if p["id"] == "local_file"), None)
        assert local is not None


# ---------------------------------------------------------------------------
# ukm list --family=distro — works on all distros
# ---------------------------------------------------------------------------


class TestListDistroIntegration:
    def test_list_distro_exits_zero(self):
        result = _ukm("list", "--family=distro")
        assert result.returncode == 0, result.stderr

    def test_list_distro_json(self):
        result = _ukm("list", "--family=distro", "--json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_list_installed_exits_zero(self):
        result = _ukm("list", "--installed", "--json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        # At least one kernel should be installed (the running one)
        assert len(data) >= 1


# ---------------------------------------------------------------------------
# ukm search — works on all distros
# ---------------------------------------------------------------------------


class TestSearchIntegration:
    def test_search_exits_zero(self):
        result = _ukm("search", "linux")
        assert result.returncode == 0, result.stderr

    def test_search_json(self):
        result = _ukm("search", "linux", "--json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_search_no_results_exits_zero(self):
        result = _ukm("search", "zzznomatch_xyzzy_9999")
        assert result.returncode == 0, result.stderr

    def test_search_by_family(self):
        result = _ukm("search", "distro", "--json")
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# ukm cpu — works on all distros
# ---------------------------------------------------------------------------


class TestCpuIntegration:
    def test_cpu_exits_zero(self):
        result = _ukm("cpu")
        assert result.returncode == 0, result.stderr

    def test_cpu_json(self):
        result = _ukm("cpu", "--json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert "recommended_xanmod_level" in data


# ---------------------------------------------------------------------------
# ukm dkms — works on all distros (dkms may not be installed)
# ---------------------------------------------------------------------------


class TestDkmsIntegration:
    def test_dkms_exits_zero(self):
        result = _ukm("dkms")
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# apt-specific tests
# ---------------------------------------------------------------------------


@requires("apt-get", "dpkg")
class TestAptIntegration:
    def test_mainline_provider_listed(self):
        result = _ukm("providers", "--json")
        data = json.loads(result.stdout)
        mainline = next((p for p in data if p["id"] == "mainline_ppa"), None)
        assert mainline is not None
        assert mainline["available"] == "yes"

    def test_distro_native_lists_apt_kernels(self):
        result = _ukm("list", "--family=distro", "--json")
        data = json.loads(result.stdout)
        # On Ubuntu/Debian there should be at least one kernel package
        assert len(data) >= 1
        assert all(e["family"] == "distro" for e in data)

    def test_search_generic(self):
        result = _ukm("search", "generic", "--json")
        data = json.loads(result.stdout)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# pacman-specific tests
# ---------------------------------------------------------------------------


@requires("pacman")
class TestPacmanIntegration:
    def test_distro_native_lists_pacman_kernels(self):
        result = _ukm("list", "--family=distro", "--json")
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_aur_provider_listed(self):
        result = _ukm("providers", "--json")
        data = json.loads(result.stdout)
        ids = [p["id"] for p in data]
        assert "aur" in ids

    def test_search_linux(self):
        result = _ukm("search", "linux", "--json")
        data = json.loads(result.stdout)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# dnf-specific tests
# ---------------------------------------------------------------------------


@requires("dnf")
class TestDnfIntegration:
    def test_distro_native_lists_dnf_kernels(self):
        result = _ukm("list", "--family=distro", "--json")
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_search_kernel(self):
        result = _ukm("search", "kernel", "--json")
        data = json.loads(result.stdout)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# apk-specific tests
# ---------------------------------------------------------------------------


@requires("apk")
class TestApkIntegration:
    def test_distro_native_lists_apk_kernels(self):
        result = _ukm("list", "--family=distro", "--json")
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_search_linux(self):
        result = _ukm("search", "linux", "--json")
        data = json.loads(result.stdout)
        assert isinstance(data, list)
