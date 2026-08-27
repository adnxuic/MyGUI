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
        self.assertEqual(len(contracts), 17)
        self.assertEqual(
            contracts[(ComponentKind.ANNOTATION, ComponentRole.ANNOTATION)],
            RestorePhase.DYNAMIC,
        )
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

    def test_register_rejects_non_component_materializer(self):
        registry = ComponentMaterializerRegistry()
        with self.assertRaisesRegex(TypeError, "requires a declaration"):
            registry.register("not-a-declaration")

    def test_materialize_dispatches_to_registered_handler_and_rejects_unregistered(self):
        registry = ComponentMaterializerRegistry()
        from mygui.figuremodify.components import ComponentState

        state = ComponentState(
            id="plot_1",
            kind=ComponentKind.LINE,
            role=ComponentRole.DATA_PLOT,
            parent_id="axes_1",
            order=0,
        )
        with self.assertRaisesRegex(
            ComponentValidationError,
            "No runtime materializer is registered for",
        ):
            registry.materialize(state, None)

        received = []
        decl = ComponentMaterializer(
            (ComponentKind.LINE, ComponentRole.DATA_PLOT),
            lambda s, t: received.append((s, t)) or "materialized",
            RestorePhase.DYNAMIC,
        )
        registry.register(decl)
        result = registry.materialize(state, "tx_dummy")
        self.assertEqual(result, "materialized")
        self.assertEqual(received, [(state, "tx_dummy")])

    def test_validate_complete_reports_all_mismatches_simultaneously(self):
        registry = ComponentMaterializerRegistry()
        key1 = (ComponentKind.LINE, ComponentRole.LINE)
        key2 = (ComponentKind.SCATTER, ComponentRole.SCATTER)
        key3 = (ComponentKind.COLORBAR, ComponentRole.COLORBAR)

        registry.register(ComponentMaterializer(key1, self.handler, RestorePhase.DYNAMIC))
        registry.register(ComponentMaterializer(key2, self.handler, RestorePhase.DYNAMIC))

        with self.assertRaises(ComponentValidationError) as ctx:
            registry.validate_complete({
                key1: RestorePhase.COLORBAR,
                key3: RestorePhase.COLORBAR,
            })
        msg = str(ctx.exception)
        self.assertIn("missing=", msg)
        self.assertIn("extra=", msg)
        self.assertIn("phase_mismatches=", msg)

    def test_keys_phases_and_states_for_phase_sorting(self):
        registry = ComponentMaterializerRegistry()
        key1 = (ComponentKind.LINE, ComponentRole.LINE)
        key2 = (ComponentKind.COLORBAR, ComponentRole.COLORBAR)
        decl1 = ComponentMaterializer(key1, self.handler, RestorePhase.DYNAMIC)
        decl2 = ComponentMaterializer(key2, self.handler, RestorePhase.COLORBAR)
        registry.register(decl1)
        registry.register(decl2)

        self.assertEqual(registry.keys, frozenset({key1, key2}))
        self.assertEqual(registry.phases, (RestorePhase.DYNAMIC, RestorePhase.COLORBAR))

        from mygui.figuremodify.components import ComponentState

        s1 = ComponentState(id="b_item", kind=ComponentKind.LINE, role=ComponentRole.LINE, parent_id="ax1", order=2)
        s2 = ComponentState(id="a_item", kind=ComponentKind.LINE, role=ComponentRole.LINE, parent_id="ax1", order=1)
        s3 = ComponentState(id="root_item", kind=ComponentKind.LINE, role=ComponentRole.LINE, parent_id=None, order=0)
        s4 = ComponentState(id="cbar_item", kind=ComponentKind.COLORBAR, role=ComponentRole.COLORBAR, parent_id="ax1", order=0)

        ordered = registry.states_for_phase([s1, s2, s3, s4], RestorePhase.DYNAMIC)
        # parent_id None becomes "", so s3 comes first, then s2 (order 1), then s1 (order 2)
        self.assertEqual(ordered, (s3, s2, s1))


if __name__ == "__main__":
    unittest.main()


