"""Tests for MainlinePPAProvider using mocked backend and network."""

from __future__ import annotations

import unittest.mock as mock
from ukm.core.kernel import KernelFamily, KernelStatus
from ukm.core.providers.mainline_ppa import MainlinePPAProvider


def make_backend(installed=None, held=None):
    b = mock.MagicMock()
    b.is_available.return_value = True
    b.installed_packages.return_value = installed or []
    b.is_held.return_value = held or False
    b._run.return_value = (0, "", "")
    return b


_FAKE_INDEX_HTML = """
<html><body>
<a href="v6.9.0/">v6.9.0/</a>
<a href="v6.8.0/">v6.8.0/</a>
<a href="v6.9.0-rc3/">v6.9.0-rc3/</a>
</body></html>
"""


class TestMainlinePPAProvider:
    def test_family(self):
        p = MainlinePPAProvider(make_backend())
        assert p.family == KernelFamily.MAINLINE

    def test_id(self):
        p = MainlinePPAProvider(make_backend())
        assert p.id == "mainline_ppa"

    def test_supported_arches(self):
        p = MainlinePPAProvider(make_backend())
        assert "amd64" in p.supported_arches
        assert "arm64" in p.supported_arches

    def test_supports_arch_amd64(self):
        p = MainlinePPAProvider(make_backend())
        assert p.supports_arch("amd64")

    def test_does_not_support_unknown_arch(self):
        p = MainlinePPAProvider(make_backend())
        assert not p.supports_arch("mips64el")

    @mock.patch("shutil.which", return_value="/usr/bin/dpkg")
    def test_is_available_with_dpkg(self, _):
        p = MainlinePPAProvider(make_backend())
        assert p.is_available()

    @mock.patch("shutil.which", return_value=None)
    def test_not_available_without_dpkg(self, _):
        p = MainlinePPAProvider(make_backend())
        assert not p.is_available()

    def test_fetch_index_parses_versions(self):
        p = MainlinePPAProvider(make_backend())
        with mock.patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = _FAKE_INDEX_HTML.encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            entries = p._fetch_index("amd64")

        versions = [str(e.version) for e in entries]
        assert "6.9.0" in versions
        assert "6.8.0" in versions
        assert "6.9.0-rc3" in versions

    def test_list_marks_running_kernel(self):
        import tempfile, json
        from pathlib import Path

        p = MainlinePPAProvider(make_backend())

        fake_entries = [
            {"version": "6.9.0", "arch": "amd64", "flavor": "generic", "source_url": None},
            {"version": "6.8.0", "arch": "amd64", "flavor": "generic", "source_url": None},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Path(tmpdir) / "index.json"
            cache.write_text(json.dumps(fake_entries))

            with (
                mock.patch("ukm.core.providers.mainline_ppa._CACHE_DIR", Path(tmpdir)),
                mock.patch("ukm.core.providers.mainline_ppa.system_info") as mock_si,
            ):
                mock_si.return_value.running_kernel = "6.9.0-061900-generic"
                mock_si.return_value.arch = "amd64"
                entries = p.list("amd64", refresh=False)

        running = [e for e in entries if e.status == KernelStatus.RUNNING]
        assert len(running) == 1
        assert str(running[0].version) == "6.9.0"

    def test_list_sorted_newest_first(self):
        import tempfile, json
        from pathlib import Path

        p = MainlinePPAProvider(make_backend())
        fake_entries = [
            {"version": "6.8.0", "arch": "amd64", "flavor": "generic", "source_url": None},
            {"version": "6.9.0", "arch": "amd64", "flavor": "generic", "source_url": None},
            {"version": "6.7.0", "arch": "amd64", "flavor": "generic", "source_url": None},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Path(tmpdir) / "index.json"
            cache.write_text(json.dumps(fake_entries))

            with (
                mock.patch("ukm.core.providers.mainline_ppa._CACHE_DIR", Path(tmpdir)),
                mock.patch("ukm.core.providers.mainline_ppa.system_info") as mock_si,
            ):
                mock_si.return_value.running_kernel = ""
                mock_si.return_value.arch = "amd64"
                entries = p.list("amd64", refresh=False)

        versions = [str(e.version) for e in entries]
        assert versions == ["6.9.0", "6.8.0", "6.7.0"]
