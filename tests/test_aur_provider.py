"""Tests for AURProvider."""

from __future__ import annotations

import unittest.mock as mock
from ukm.core.kernel import KernelFamily, KernelStatus
from ukm.core.providers.aur import AURProvider, _aur_helper


def make_backend():
    b = mock.MagicMock()
    b.is_available.return_value = True
    b.is_held.return_value = False
    b._run.return_value = (1, "", "")  # not installed by default
    return b


class TestAURProvider:
    def test_id(self):
        assert AURProvider(make_backend()).id == "aur"

    def test_family(self):
        assert AURProvider(make_backend()).family == KernelFamily.DISTRO

    def test_supported_arches(self):
        p = AURProvider(make_backend())
        assert "amd64" in p.supported_arches
        assert "arm64" in p.supported_arches

    @mock.patch("shutil.which", side_effect=lambda x: "/usr/bin/yay" if x == "yay" else None)
    def test_helper_prefers_yay(self, _):
        assert _aur_helper() == "yay"

    @mock.patch("shutil.which", side_effect=lambda x: "/usr/bin/paru" if x == "paru" else None)
    def test_helper_falls_back_to_paru(self, _):
        assert _aur_helper() == "paru"

    @mock.patch("shutil.which", return_value=None)
    def test_no_helper(self, _):
        assert _aur_helper() is None

    @mock.patch("shutil.which", return_value=None)
    def test_not_available_without_pacman(self, _):
        assert not AURProvider(make_backend()).is_available()

    @mock.patch(
        "shutil.which", side_effect=lambda x: "/usr/bin/" + x if x in ("pacman", "yay") else None
    )
    def test_available_with_pacman_and_yay(self, _):
        assert AURProvider(make_backend()).is_available()

    @mock.patch("ukm.core.providers.aur.system_info")
    @mock.patch("ukm.core.providers.aur._aur_helper", return_value="yay")
    def test_list_marks_installed(self, _helper, mock_si):
        mock_si.return_value.running_kernel = ""

        backend = make_backend()

        # Simulate linux-cachyos installed
        def run_side(cmd, **kwargs):
            if "pacman" in cmd and "-Q" in cmd and "linux-cachyos" in cmd:
                return (0, "linux-cachyos 6.9.0.cachyos1-1", "")
            if "yay" in cmd and "-Si" in cmd:
                return (0, "Version : 6.9.0.cachyos1-1\n", "")
            return (1, "", "")

        backend._run.side_effect = run_side

        p = AURProvider(backend)
        entries = p.list("amd64")

        installed = [e for e in entries if e.status == KernelStatus.INSTALLED]
        assert any(e.flavor == "linux-cachyos" for e in installed)

    def test_aur_rpc_version(self):
        import json

        fake_response = json.dumps({"results": [{"Version": "6.9.0.cachyos1-1"}]}).encode()

        with mock.patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = fake_response
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            ver = AURProvider._aur_rpc_version("linux-cachyos")

        assert ver == "6.9.0.cachyos1-1"

    def test_aur_rpc_version_network_failure(self):
        with mock.patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            ver = AURProvider._aur_rpc_version("linux-cachyos")
        assert ver == ""
