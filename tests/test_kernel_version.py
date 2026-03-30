"""Tests for KernelVersion parsing and ordering."""

from ukm.core.kernel import KernelVersion


def v(s: str) -> KernelVersion:
    return KernelVersion(s)


class TestParsing:
    def test_simple(self):
        kv = v("6.9.0")
        assert kv.major == 6
        assert kv.minor == 9
        assert kv.patch == 0
        assert kv.pre is None

    def test_rc(self):
        kv = v("6.9.0-rc3")
        assert kv.major == 6
        assert kv.minor == 9
        assert kv.patch == 0
        assert kv.pre == "rc3"

    def test_no_patch(self):
        kv = v("6.9")
        assert kv.major == 6
        assert kv.minor == 9
        assert kv.patch == 0

    def test_with_suffix(self):
        kv = v("6.8.0-061800-generic")
        assert kv.major == 6
        assert kv.minor == 8
        assert kv.patch == 0

    def test_str_roundtrip(self):
        raw = "6.9.0-rc3"
        assert str(v(raw)) == raw


class TestOrdering:
    def test_release_gt_rc(self):
        assert v("6.9.0") > v("6.9.0-rc3")

    def test_rc_ordering(self):
        assert v("6.9.0-rc3") > v("6.9.0-rc1")

    def test_major_ordering(self):
        assert v("7.0.0") > v("6.9.9")

    def test_minor_ordering(self):
        assert v("6.10.0") > v("6.9.0")

    def test_patch_ordering(self):
        assert v("6.9.3") > v("6.9.1")

    def test_equality(self):
        assert v("6.9.0") == v("6.9.0")
        assert v("6.9.0-rc1") == v("6.9.0-rc1")

    def test_sort(self):
        versions = ["6.9.0-rc1", "6.9.0", "6.8.0", "6.9.0-rc3", "7.0.0"]
        expected = ["7.0.0", "6.9.0", "6.9.0-rc3", "6.9.0-rc1", "6.8.0"]
        result = [str(x) for x in sorted([v(s) for s in versions], reverse=True)]
        assert result == expected

    def test_pre_lt_release(self):
        assert v("6.9.0-pre1") < v("6.9.0-rc1") < v("6.9.0")
