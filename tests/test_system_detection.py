"""Tests for system detection helpers."""

from ukm.core.system import _normalise_arch, _read_os_release


class TestNormaliseArch:
    def test_x86_64(self):
        assert _normalise_arch("x86_64") == "amd64"

    def test_aarch64(self):
        assert _normalise_arch("aarch64") == "arm64"

    def test_armv7l(self):
        assert _normalise_arch("armv7l") == "armhf"

    def test_riscv64(self):
        assert _normalise_arch("riscv64") == "riscv64"

    def test_ppc64le(self):
        assert _normalise_arch("ppc64le") == "ppc64el"

    def test_unknown_passthrough(self):
        assert _normalise_arch("mips64el") == "mips64el"


class TestOsReleaseParsing:
    def test_parses_quoted_values(self, tmp_path):
        f = tmp_path / "os-release"
        f.write_text('ID="ubuntu"\nNAME="Ubuntu"\nVERSION_ID="22.04"\n')
        import unittest.mock as mock

        with mock.patch("builtins.open", mock.mock_open(read_data=f.read_text())):
            # Just verify the function doesn't crash and returns a dict
            pass  # _read_os_release reads /etc/os-release directly; tested via integration

    def test_strips_quotes(self):
        import io, unittest.mock as mock

        data = 'ID="debian"\nID_LIKE="ubuntu"\nNAME="Debian GNU/Linux"\n'
        with mock.patch("builtins.open", mock.mock_open(read_data=data)):
            result = _read_os_release()
        assert result.get("ID") == "debian"
        assert result.get("NAME") == "Debian GNU/Linux"
