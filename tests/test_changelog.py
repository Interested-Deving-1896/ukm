"""Tests for the changelog fetcher."""

from __future__ import annotations

import tempfile
import unittest.mock as mock
from pathlib import Path

from ukm.core.changelog import _fetch_liquorix, _fetch_mainline, clear_cache, fetch


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
            with (
                mock.patch("ukm.core.changelog._CACHE_DIR", cache_dir),
                mock.patch(
                    "ukm.core.changelog._fetch_remote", return_value="remote text"
                ) as mock_fetch,
            ):
                result = fetch("mainline_ppa", "6.9.0")
                assert result == "remote text"
                mock_fetch.assert_called_once_with("mainline_ppa", "6.9.0", "")

    def test_result_written_to_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            with (
                mock.patch("ukm.core.changelog._CACHE_DIR", cache_dir),
                mock.patch("ukm.core.changelog._fetch_remote", return_value="fresh text"),
            ):
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
            with (
                mock.patch("ukm.core.changelog._CACHE_DIR", cache_dir),
                mock.patch("ukm.core.changelog._fetch_remote", return_value=""),
            ):
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
            b"--- 6.9.0-1 ---\n"
            b"- Improved scheduler\n"
            b"- Updated MuQSS\n"
            b"---\n"
            b"--- 6.8.0-1 ---\n"
            b"- Previous release\n"
        )

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
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            mock.patch("ukm.core.changelog._CACHE_DIR", Path(tmpdir)),
        ):
            result = fetch("unknown_provider", "6.9.0")
        assert result == ""


# ---------------------------------------------------------------------------
# Additional fetcher tests
# ---------------------------------------------------------------------------


class TestXanmodFetcher:
    def test_returns_fallback_url_when_no_match(self):
        from ukm.core.changelog import _fetch_xanmod

        html = b"<html><body>XanMod kernel page</body></html>"
        with mock.patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = html
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = _fetch_xanmod("6.9.0", "")
        assert "xanmod.org" in result

    def test_returns_empty_on_network_error(self):
        from ukm.core.changelog import _fetch_xanmod

        with mock.patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = _fetch_xanmod("6.9.0", "")
        assert result == ""

    def test_extracts_version_mention(self):
        from ukm.core.changelog import _fetch_xanmod

        html = b"<html><body>\nKernel 6.9.0 released with improvements\n</body></html>"
        with mock.patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = html
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = _fetch_xanmod("6.9.0", "")
        assert "6.9.0" in result


class TestDistroNativeFetcher:
    def test_returns_empty_when_no_doc_and_no_apt(self):
        from ukm.core.changelog import _fetch_distro_native

        with (
            mock.patch("pathlib.Path.exists", return_value=False),
            mock.patch("shutil.which", return_value=None),
        ):
            result = _fetch_distro_native("6.9.0", "generic")
        assert result == ""

    def test_reads_local_gzip_changelog(self):
        import gzip

        from ukm.core.changelog import _fetch_distro_native

        content = b"Kernel changelog entry\n"
        gz_data = gzip.compress(content)

        with tempfile.TemporaryDirectory() as tmpdir:
            doc_dir = Path(tmpdir) / "linux-image-6.9.0-generic"
            doc_dir.mkdir()
            gz_file = doc_dir / "changelog.Debian.gz"
            gz_file.write_bytes(gz_data)

            with mock.patch(
                "ukm.core.changelog.Path",
                side_effect=lambda p: Path(p.replace("/usr/share/doc", tmpdir)),
            ):
                # Direct call with patched path
                pass

        # Test via direct gzip read path
        with tempfile.TemporaryDirectory() as tmpdir:
            doc_dir = Path(tmpdir) / "linux-image-6.9.0-generic"
            doc_dir.mkdir()
            gz_file = doc_dir / "changelog.Debian.gz"
            gz_file.write_bytes(gz_data)
            # Patch the Path constructor used inside _fetch_distro_native
            original_path = __import__("pathlib").Path

            def patched_path(p):
                if "/usr/share/doc" in str(p):
                    return original_path(str(p).replace("/usr/share/doc", tmpdir))
                return original_path(p)

            with mock.patch("ukm.core.changelog.Path", side_effect=patched_path):
                result = _fetch_distro_native("6.9.0", "generic")
            assert "Kernel changelog" in result

    def test_network_error_returns_empty(self):
        from ukm.core.changelog import _fetch_distro_native

        with (
            mock.patch("pathlib.Path.exists", return_value=False),
            mock.patch("shutil.which", return_value="/usr/bin/apt-get"),
            mock.patch("urllib.request.urlopen", side_effect=Exception("timeout")),
        ):
            result = _fetch_distro_native("6.9.0", "generic")
        assert result == ""


class TestAurFetcher:
    def test_extracts_commit_messages(self):
        from ukm.core.changelog import _fetch_aur

        html = b"""<html><body>
        <td class='subject'><a href='/log'>Update to 6.9.0</a></td>
        <td class='subject'><a href='/log'>Fix build</a></td>
        </body></html>"""
        with mock.patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = html
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = _fetch_aur("6.9.0", "linux-zen")
        assert "Update to 6.9.0" in result

    def test_returns_fallback_url_when_no_commits(self):
        from ukm.core.changelog import _fetch_aur

        html = b"<html><body>no commits here</body></html>"
        with mock.patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = html
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = _fetch_aur("6.9.0", "linux-zen")
        assert "aur.archlinux.org" in result

    def test_returns_empty_on_network_error(self):
        from ukm.core.changelog import _fetch_aur

        with mock.patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = _fetch_aur("6.9.0", "linux-zen")
        assert result == ""


class TestGentooFetcher:
    def test_extracts_commit_messages(self):
        from ukm.core.changelog import _fetch_gentoo

        html = b"""<html><body>
        <td class="subject"><a href="/log">sys-kernel/gentoo-sources-6.9.0</a></td>
        </body></html>"""
        with mock.patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = html
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = _fetch_gentoo("6.9.0", "")
        assert "gentoo-sources" in result

    def test_returns_fallback_url_when_no_commits(self):
        from ukm.core.changelog import _fetch_gentoo

        html = b"<html><body>nothing</body></html>"
        with mock.patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = html
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = mock.MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = _fetch_gentoo("6.9.0", "")
        assert "packages.gentoo.org" in result

    def test_returns_empty_on_network_error(self):
        from ukm.core.changelog import _fetch_gentoo

        with mock.patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = _fetch_gentoo("6.9.0", "")
        assert result == ""


class TestFetchWithFlavor:
    def test_flavor_included_in_cache_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            with (
                mock.patch("ukm.core.changelog._CACHE_DIR", cache_dir),
                mock.patch("ukm.core.changelog._fetch_remote", return_value="rt notes"),
            ):
                result = fetch("xanmod", "6.9.0", "rt")
                cache_file = cache_dir / "xanmod" / "6.9.0-rt.txt"
                assert cache_file.exists()
                assert result == "rt notes"

    def test_exception_in_fetcher_returns_error_string(self):
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            mock.patch("ukm.core.changelog._CACHE_DIR", Path(tmpdir)),
            mock.patch(
                "ukm.core.changelog._fetch_mainline", side_effect=RuntimeError("boom")
            ),
        ):
            result = fetch("mainline_ppa", "6.9.0")
        assert "Could not fetch" in result
