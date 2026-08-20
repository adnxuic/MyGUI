"""Fixture: a production violation."""
class Panel(QFrame):
    def mutate(self, line):
        line.set_visible(False)
