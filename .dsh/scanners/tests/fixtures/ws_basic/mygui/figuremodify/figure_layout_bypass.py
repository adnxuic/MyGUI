"""Positive fixture for ARCH-FIGURE-LAYOUT-ENGINE-BYPASS."""


def retired_proxy_field(constrained_layout: bool = False):
    return constrained_layout


class AxesLayoutService:
    def mutate_engine_call(self, figure):
        figure.set_layout_engine("constrained")

    def mutate_engine_prop(self, root_ctrl):
        root_ctrl.set_property("layout_engine", {"kind": "tight", "params": {}})

    def mutate_layouts_apply_state(self, root_ctrl, state):
        root_ctrl.apply_state(state)
