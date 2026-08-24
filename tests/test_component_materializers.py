import unittest

from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    ComponentValidationError,
    RestorePhase,
    validate_controller_contracts,
)
from mygui.widgets.figure_canvas.component_materializers import (
    ComponentMaterializer,
    ComponentMaterializerRegistry,
)


class ComponentMaterializerContractTests(unittest.TestCase):
    def setUp(self):
        self.key = (ComponentKind.LINE, ComponentRole.LINE)
        self.handler = lambda _state, _transaction: None

    def test_controller_contract_is_independent_completeness_source(self):
        contracts = validate_controller_contracts()
        self.assertEqual(len(contracts), 13)
        self.assertEqual(
            contracts[
                (
                    ComponentKind.REFERENCE_GUIDE,
                    ComponentRole.REFERENCE_LINE,
                )
            ],
            RestorePhase.DYNAMIC,
        )
        self.assertEqual(
            contracts[
                (
                    ComponentKind.REFERENCE_GUIDE,
                    ComponentRole.REFERENCE_BAND,
                )
            ],
            RestorePhase.DYNAMIC,
        )
        self.assertEqual(
            contracts[
                (
                    ComponentKind.REFERENCE_MARKS,
                    ComponentRole.REFLECTION_POSITIONS,
                )
            ],
            RestorePhase.DYNAMIC,
        )
        self.assertEqual(
            contracts[(ComponentKind.COLORBAR, ComponentRole.COLORBAR)],
            RestorePhase.COLORBAR,
        )
        self.assertEqual(
            contracts[(ComponentKind.IN_AXES, ComponentRole.IN_AXES_IMAGE)],
            RestorePhase.IN_AXES,
        )

    def test_registry_rejects_duplicate_non_callable_and_bad_phase(self):
        registry = ComponentMaterializerRegistry()
        declaration = ComponentMaterializer(
            self.key,
            self.handler,
            RestorePhase.DYNAMIC,
        )
        registry.register(declaration)
        with self.assertRaisesRegex(ComponentValidationError, "Duplicate"):
            registry.register(declaration)
        with self.assertRaisesRegex(ComponentValidationError, "callable"):
            ComponentMaterializer(self.key, None, RestorePhase.DYNAMIC)
        with self.assertRaisesRegex(ComponentValidationError, "phase"):
            ComponentMaterializer(self.key, self.handler, 999)

    def test_completeness_rejects_missing_extra_and_phase_mismatch(self):
        registry = ComponentMaterializerRegistry()
        with self.assertRaisesRegex(ComponentValidationError, "missing"):
            registry.validate_complete({self.key: RestorePhase.DYNAMIC})

        registry.register(
            ComponentMaterializer(
                self.key,
                self.handler,
                RestorePhase.DYNAMIC,
            )
        )
        with self.assertRaisesRegex(ComponentValidationError, "extra"):
            registry.validate_complete({})
        with self.assertRaisesRegex(
            ComponentValidationError,
            "phase_mismatches",
        ):
            registry.validate_complete({self.key: RestorePhase.IN_AXES})


if __name__ == "__main__":
    unittest.main()
