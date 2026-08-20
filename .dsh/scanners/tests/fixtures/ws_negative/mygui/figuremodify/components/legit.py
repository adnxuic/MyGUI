"""Negative fixture: domain layer may mutate artists and state."""
class LineController:
    def apply(self, artist):
        artist.set_visible(True)
        artist.set_linewidth(2.0)

    def mutate_state(self, state):
        state.properties["visible"] = True
        state.data.update({"x": 1})
