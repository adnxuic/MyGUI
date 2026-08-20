"""Fixture: test-code accesses private container state."""
import matplotlib as mpl


class TestUi:
    def test_private(self, host):
        count = host._figure_stack.count()
        assert count == 0

    def test_rcparams_fixture(self):
        mpl.rcParams["text.usetex"] = True  # test-only setup: not a production finding
