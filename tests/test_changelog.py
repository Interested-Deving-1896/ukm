"""Tests for the changelog fetcher."""

from __future__ import annotations

import tempfile
import unittest.mock as mock
from pathlib import Path

from ukm.core.changelog import fetch, clear_cache, _fetch_mainline, _fetch_liquorix


class TestChangelogCache:

    def test_cached_result_returned(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            with mock.patch("ukm.core.changelog._CACHE_DIR", cache_dir):
                # Prime the cache manually
                cache_file = cache_dir / "mainline_ppa" / "6.9.0.txt"
                cache_file.parent.mkdir(parents=True)
                cache_file.write_text("cached changelog text")

                result = fetch("mainline_ppa", "6.9.0")
                assert result == "cached changelog text"

    def test_cache_miss_calls_remote(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            with mock.patch("ukm.core.changelog._CACHE_DIR", cache_dir), \
                 mock.patch("ukm.core.changelog._fetch_remote", return_value="remote text") as mock_fetch:
                result = fetch("mainline_ppa", "6.9.0")
                assert result == "remote text"
                mock_fetch.assert_called_once_with("mainline_ppa", "6.9.0", "")

    def test_result_written_to_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            with mock.patch("ukm.core.changelog._CACHE_DIR", cache_dir), \
                 mock.patch("ukm.core.changelog._fetch_remote", return_value="fresh text"):
                fetch("mainline_ppa", "6.9.0")
                cache_file = cache_dir / "mainline_ppa" / "6.9.0.txt"
                assert cache_file.exists()
                assert cache_file.read_text() == "fresh text"

    def test_clear_cache_removes_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            f = cache_dir / "mainline_ppa" / "6.9.0.txt"
            f.parent.mkdir(parents=True)
            f.write_text("text")
            with mock.patch("ukm.core.changelog._CACHE_DIR", cache_dir):
                removed = clear_cache("mainline_ppa")
            assert removed == 1
            assert not f.exists()

    def test_clear_all_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            for provider in ("mainline_ppa", "xanmod"):
                d = cache_dir / provider
                d.mkdir(parents=True)
                (d / "6.9.0.txt").write_text("text")
            with mock.patch("ukm.core.changelog._CACHE_DIR", cache_dir):
                removed = clear_cache()
            assert removed == 2

    def test_empty_remote_not_cached(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            with mock.patch("ukm.core.changelog._CACHE_DIR", cache_dir), \
                 mock.patch("ukm.core.changelog._fetch_remote", return_value=""):
                result = fetch("mainline_ppa", "6.9.0")
                assert result == ""
                cache_file = cache_dir / "mainline_ppa" / "6.9.0.txt"
                assert not cache_file.exists()


class TestMainlineFetcher:

    def test_fetches_changes_file(self):
        fake_content = b"Linux 6.9 release notes\n- fix A\n- fix B\n"
        with mock.patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = fake_content
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            result = _fetch_mainline("6.9.0", "generic")

        assert "Linux 6.9" in result

    def test_returns_empty_on_network_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = _fetch_mainline("6.9.0", "generic")
        assert result == ""


class TestLiquorixFetcher:

    def test_extracts_version_section(self):
        fake_changelog = (
            "--- 6.9.0-1 ---\n"
            "- Improved scheduler\n"
            "- Updated MuQSS\n"
            "---\n"
            "--- 6.8.0-1 ---\n"
            "- Previous release\n"
        ).encode()

        with mock.patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = fake_changelog
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            result = _fetch_liquorix("6.9.0", "liquorix")

        assert "Improved scheduler" in result
        # Should not include the 6.8.0 section
        assert "Previous release" not in result

    def test_returns_empty_on_network_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = _fetch_liquorix("6.9.0", "liquorix")
        assert result == ""


class TestUnknownProvider:

    def test_unknown_provider_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("ukm.core.changelog._CACHE_DIR", Path(tmpdir)):
                result = fetch("unknown_provider", "6.9.0")
        assert result == ""
