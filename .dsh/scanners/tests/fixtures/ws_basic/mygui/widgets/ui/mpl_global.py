"""Fixture: UI mutation of Matplotlib process-global configuration."""
import matplotlib as mpl
from matplotlib import rcParams
from matplotlib import rc


class MplGlobalPanel(QFrame):
    def assign_via_module(self):
        mpl.rcParams["text.usetex"] = True  # violation: assignment

    def assign_via_import(self):
        rcParams["text.usetex"] = True  # violation: assignment

    def update_via_module(self):
        mpl.rcParams.update({"text.usetex": True})  # violation: update

    def rc_via_module(self):
        mpl.rc("text", usetex=True)  # violation: rc-call

    def rc_via_import(self):
        rc("text", usetex=True)  # violation: rc-call

    def read_ok(self):
        return mpl.rcParams["text.usetex"]  # legal: read-only

    def read_get_ok(self):
        return rcParams.get("text.usetex")  # legal: read-only
