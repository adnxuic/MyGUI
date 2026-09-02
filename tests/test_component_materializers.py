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
        self.assertEqual(len(contracts), 20)
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
        self.assertEqual(
            contracts[
                (ComponentKind.SECONDARY_AXIS, ComponentRole.SECONDARY_X_AXIS)
            ],
            RestorePhase.SECONDARY_AXIS,
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


class ComponentContractAuditTests(unittest.TestCase):
    def test_production_contracts_are_complete_without_becoming_state(self):
        from mygui.figuremodify.component_services import production_deletion_handlers
        from mygui.figuremodify.components import (
            ComponentContractAuditRow,
            require_complete_component_contracts,
        )
        from mygui.figuremodify.components.models import DeletionPolicy, ROLES_BY_KIND
        from mygui.widgets.fig_control_window.component_editors import (
            EditorRegistry,
            register_production_profiles,
        )

        registry = EditorRegistry()
        register_production_profiles(registry)
        handlers = production_deletion_handlers()
        rows = require_complete_component_contracts(
            editor_profile_keys=registry.profile_keys,
            materializer_keys=validate_controller_contracts(),
            deletion_handler_keys=handlers.keys,
        )
        self.assertTrue(rows)
        self.assertTrue(all(isinstance(row, ComponentContractAuditRow) for row in rows))
        self.assertTrue(all(row.complete for row in rows))
        expected = {
            (kind, role)
            for kind, roles in ROLES_BY_KIND.items()
            for role in roles
        }
        self.assertEqual({(row.kind, row.role) for row in rows}, expected)
        hide_rows = [row for row in rows if row.deletion_policy is DeletionPolicy.HIDE]
        self.assertTrue(hide_rows)
        self.assertTrue(all(not row.has_deletion_handler for row in hide_rows))

    def test_audit_reports_incomplete_editor_coverage(self):
        from mygui.figuremodify.components import (
            ComponentKind,
            ComponentRole,
            ComponentValidationError,
            require_complete_component_contracts,
        )

        with self.assertRaisesRegex(ComponentValidationError, "Incomplete"):
            require_complete_component_contracts(
                editor_profile_keys=(),
                materializer_keys=validate_controller_contracts(),
                deletion_handler_keys=(),
            )
        from mygui.figuremodify.components import audit_component_contracts

        rows = audit_component_contracts(
            editor_profile_keys=(),
            materializer_keys=validate_controller_contracts(),
            deletion_handler_keys=(),
        )
        line = next(
            row
            for row in rows
            if row.kind is ComponentKind.LINE and row.role is ComponentRole.LINE
        )
        self.assertFalse(line.complete)
        self.assertFalse(line.has_editor_profile)


if __name__ == "__main__":
    unittest.main()



