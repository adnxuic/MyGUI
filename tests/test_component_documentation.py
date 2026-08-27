"""Tests verifying the MkDocs component documentation contract."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

from mygui.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    CONTROLLER_TYPES,
    ROLES_BY_KIND,
)
from mygui.widgets.fig_control_window.component_editors.profiles import (
    register_production_profiles,
)
from mygui.widgets.fig_control_window.component_editors.registry import (
    EDITABLE_DATA_KEYS,
    EditorRegistry,
    PROXY_KEYS,
)


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
SNIPPETS_DIR = DOCS_DIR / "_snippets"
MKDOCS_YML = ROOT / "mkdocs.yml"

# Checked-in mapping of the 31 production Inspector profiles onto their
# dedicated MkDocs pages. CI must not read generated files under build/.
PROFILE_DOC_PAGES: dict[tuple[str, str], str] = {
    ("annotation", "annotation"): "editing-components/elements/annotation.md",
    ("axes", "axes"): "editing-components/fixed-semantics/axes.md",
    ("axis", "x_axis"): "editing-components/fixed-semantics/x-axis/index.md",
    ("axis", "y_axis"): "editing-components/fixed-semantics/y-axis/index.md",
    ("colorbar", "colorbar"): "editing-components/elements/colorbar.md",
    ("figure", "figure"): "editing-components/fixed-semantics/figure.md",
    ("grid", "grid"): "editing-components/fixed-semantics/x-axis/major-grid.md",
    ("in_axes", "in_axes_image"): "editing-components/elements/in-axes-image.md",
    ("in_axes", "in_axes_zoom"): "editing-components/elements/in-axes-zoom.md",
    ("legend", "legend"): "editing-components/fixed-semantics/axes-structure/legend.md",
    ("line", "data_plot"): "editing-components/charts/plot.md",
    ("line", "fit_curve"): "editing-components/charts/fit-curve.md",
    ("line", "function_curve"): "editing-components/charts/function-curve.md",
    ("line", "interpolation"): "editing-components/charts/interpolation.md",
    ("line", "line"): "editing-components/charts/line.md",
    ("reference_guide", "reference_band"): "editing-components/elements/reference-band.md",
    ("reference_guide", "reference_line"): "editing-components/elements/reference-line.md",
    ("reference_marks", "reflection_positions"): "editing-components/elements/reflection-positions.md",
    ("scatter", "scatter"): "editing-components/charts/scatter.md",
    ("field_2d", "pseudocolor"): "editing-components/charts/pseudocolor.md",
    ("field_2d", "heatmap"): "editing-components/charts/heatmap.md",
    ("field_2d", "contour"): "editing-components/charts/contour.md",
    ("spine", "spine"): "editing-components/fixed-semantics/axes-structure/spine.md",
    ("text", "text"): "editing-components/elements/text.md",
    ("text", "title"): "editing-components/fixed-semantics/axes-structure/title.md",
    ("text", "x_label"): "editing-components/fixed-semantics/x-axis/x-label.md",
    ("text", "y_label"): "editing-components/fixed-semantics/y-axis/y-label.md",
    ("tick_group", "major_tick"): "editing-components/fixed-semantics/x-axis/major-ticks.md",
    ("tick_group", "minor_tick"): "editing-components/fixed-semantics/x-axis/minor-ticks.md",
    ("tick_label_group", "major_tick_label"): "editing-components/fixed-semantics/x-axis/major-tick-labels.md",
    ("tick_label_group", "minor_tick_label"): "editing-components/fixed-semantics/x-axis/minor-tick-labels.md",
}

EXPECTED_TABLE_HEADERS = (
    "Inspector field",
    "Control",
    "Meaning",
    "Values / default",
    "Persisted / runtime key",
)

SNIPPET_LINE_PATTERN = re.compile(r'^[ \t]*--8<--\s+["\']([^"\']+)["\']', re.MULTILINE)


class _MkDocsYamlLoader(yaml.SafeLoader):
    """YAML loader supporting custom Python tags in mkdocs.yml."""


_MkDocsYamlLoader.add_multi_constructor(
    "tag:yaml.org,2002:python/name:",
    lambda loader, suffix, node: suffix,
)


def _expand_snippets(content: str, base_dir: Path = DOCS_DIR, visited: set[Path] | None = None) -> str:
    """Recursively expand pymdownx snippet directives matching line-start syntax."""
    if visited is None:
        visited = set()

    def _replace(match: re.Match) -> str:
        snippet_ref = match.group(1).strip()
        candidate = base_dir / snippet_ref
        if not candidate.exists():
            candidate = DOCS_DIR / snippet_ref.lstrip("/")
        if not candidate.exists():
            candidate = ROOT / snippet_ref
        if not candidate.exists():
            raise FileNotFoundError(f"Snippet file not found: {snippet_ref}")

        resolved = candidate.resolve()
        if resolved in visited:
            raise ValueError(f"Circular snippet inclusion detected: {snippet_ref}")

        snippet_text = resolved.read_text(encoding="utf-8")
        return _expand_snippets(snippet_text, base_dir, visited | {resolved})

    return SNIPPET_LINE_PATTERN.sub(_replace, content)


def _extract_markdown_tables(markdown_text: str) -> list[tuple[list[str], list[list[str]]]]:
    """Extract all markdown tables as (headers, rows)."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = markdown_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and line.endswith("|") and "|" in line[1:-1]:
            headers = [c.strip() for c in line[1:-1].split("|")]
            if i + 1 < len(lines):
                sep_line = lines[i + 1].strip()
                if sep_line.startswith("|") and sep_line.endswith("|"):
                    sep_cells = [c.strip() for c in sep_line[1:-1].split("|")]
                    if len(sep_cells) == len(headers) and all(
                        re.match(r"^:?-+:?$", c) for c in sep_cells
                    ):
                        rows: list[list[str]] = []
                        i += 2
                        while i < len(lines):
                            row_line = lines[i].strip()
                            if row_line.startswith("|") and row_line.endswith("|"):
                                row_cells = [c.strip() for c in row_line[1:-1].split("|")]
                                rows.append(row_cells)
                                i += 1
                            else:
                                break
                        tables.append((headers, rows))
                        continue
        i += 1
    return tables


def _normalize_key_name(raw_key: str) -> str:
    """Normalize persisted/runtime key from table cell (e.g. `properties.xlim` -> `xlim`)."""
    cleaned = raw_key.strip("` \t\r\n")
    if cleaned.startswith("properties."):
        return cleaned[len("properties."):]
    if cleaned.startswith("data."):
        return cleaned[len("data."):]
    if cleaned.startswith("runtime."):
        return cleaned[len("runtime."):]
    return cleaned


class ComponentDocumentationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = EditorRegistry()
        register_production_profiles(cls.registry)
        cls.registry.freeze()
        cls.doc_pages_by_key = dict(PROFILE_DOC_PAGES)

    def _resolve_doc_path(self, doc_page_rel: str) -> Path:
        p = DOCS_DIR / doc_page_rel.removeprefix("docs/")
        if not p.exists():
            p = ROOT / doc_page_rel
        return p

    def test_all_31_inspector_profiles_have_dedicated_pages(self):
        """Validate all 31 registered production EditorProfiles have dedicated doc pages."""
        all_expected_keys = {
            (kind, role)
            for kind, roles in ROLES_BY_KIND.items()
            for role in roles
        }
        self.assertEqual(len(all_expected_keys), 31)

        for kind, role in all_expected_keys:
            profile = self.registry.profile_for(kind, role)
            self.assertIsNotNone(
                profile,
                f"Missing registered profile for {kind.value}:{role.value}",
            )

        seen_pages = set()
        for kind, role in all_expected_keys:
            doc_rel = self.doc_pages_by_key.get((kind.value, role.value))
            self.assertIsNotNone(
                doc_rel,
                f"No doc page mapped in contract for {kind.value}:{role.value}",
            )
            doc_path = self._resolve_doc_path(doc_rel)
            self.assertTrue(
                doc_path.is_file(),
                f"Documentation page not found: {doc_path} for {kind.value}:{role.value}",
            )
            self.assertNotIn(
                doc_path.resolve(),
                seen_pages,
                f"Duplicate doc page mapped to multiple profiles: {doc_path}",
            )
            seen_pages.add(doc_path.resolve())

        self.assertEqual(len(seen_pages), 31)

    def test_parameter_tables_strictly_follow_5_column_format(self):
        """Validate all parameter tables adhere to standard 5-column format."""
        for (kind_str, role_str), doc_rel in self.doc_pages_by_key.items():
            doc_path = self._resolve_doc_path(doc_rel)
            raw_text = doc_path.read_text(encoding="utf-8")
            expanded_text = _expand_snippets(raw_text, base_dir=DOCS_DIR)

            tables = _extract_markdown_tables(expanded_text)
            self.assertTrue(
                len(tables) >= 1,
                f"Page {doc_rel} contains no markdown tables",
            )

            for headers, rows in tables:
                if any("inspector field" in h.lower() for h in headers) or any("persisted" in h.lower() for h in headers):
                    self.assertEqual(
                        len(headers),
                        5,
                        f"Parameter table in {doc_rel} does not have 5 columns: {headers}",
                    )
                    for col_idx, expected_header in enumerate(EXPECTED_TABLE_HEADERS):
                        self.assertEqual(
                            headers[col_idx].strip().lower(),
                            expected_header.lower(),
                            f"Column {col_idx + 1} header in {doc_rel} is '{headers[col_idx]}', expected '{expected_header}'",
                        )
                    for row_idx, row in enumerate(rows):
                        self.assertEqual(
                            len(row),
                            5,
                            f"Row {row_idx + 1} in {doc_rel} does not have 5 cells: {row}",
                        )
                        for cell_idx, cell in enumerate(row):
                            self.assertTrue(
                                bool(cell.strip()),
                                f"Row {row_idx + 1} cell {cell_idx + 1} in {doc_rel} is empty",
                            )

    def test_every_property_spec_and_section_key_appears_exactly_once(self):
        """Validate 100% of controller PropertySpecs and section keys appear exactly once."""
        for kind, roles in ROLES_BY_KIND.items():
            for role in roles:
                doc_rel = self.doc_pages_by_key[(kind.value, role.value)]
                doc_path = self._resolve_doc_path(doc_rel)
                raw_text = doc_path.read_text(encoding="utf-8")
                expanded_text = _expand_snippets(raw_text, base_dir=DOCS_DIR)

                controller_cls = CONTROLLER_TYPES.get((kind, role))
                self.assertIsNotNone(controller_cls, f"No controller for {kind.value}:{role.value}")

                expected_spec_keys = {spec.key for spec in controller_cls.PROPERTY_SPECS}
                expected_data_keys = set(EDITABLE_DATA_KEYS.get((kind, role), frozenset()))
                expected_proxy_keys = set(PROXY_KEYS.get((kind, role), frozenset()))

                all_expected_keys = expected_spec_keys | expected_data_keys | expected_proxy_keys

                tables = _extract_markdown_tables(expanded_text)
                documented_keys: list[str] = []
                for headers, rows in tables:
                    if len(headers) == 5 and "persisted" in headers[4].lower():
                        for row in rows:
                            key_cell = row[4]
                            norm_key = _normalize_key_name(key_cell)
                            documented_keys.append(norm_key)

                duplicates = [k for k in documented_keys if documented_keys.count(k) > 1]
                self.assertEqual(
                    duplicates,
                    [],
                    f"Duplicate property keys in {doc_rel} for {kind.value}:{role.value}: {set(duplicates)}",
                )

                documented_set = set(documented_keys)

                missing = all_expected_keys - documented_set
                self.assertEqual(
                    missing,
                    set(),
                    f"Missing property keys in {doc_rel} for {kind.value}:{role.value}: {missing}",
                )

                unexpected = documented_set - all_expected_keys
                self.assertEqual(
                    unexpected,
                    set(),
                    f"Unexpected property keys in {doc_rel} for {kind.value}:{role.value}: {unexpected}",
                )

    def test_schema_v15_special_keys_documented(self):
        """Validate specific schema v15 keys are present and correctly documented."""
        v15_cases = [
            (ComponentKind.AXES, ComponentRole.AXES, "y_lower_reserve"),
            (ComponentKind.REFERENCE_MARKS, ComponentRole.REFLECTION_POSITIONS, "position_ref"),
            (ComponentKind.REFERENCE_MARKS, ComponentRole.REFLECTION_POSITIONS, "placement"),
            (ComponentKind.LEGEND, ComponentRole.LEGEND, "entry_scope"),
        ]
        for kind, role, key_name in v15_cases:
            doc_rel = self.doc_pages_by_key[(kind.value, role.value)]
            doc_path = self._resolve_doc_path(doc_rel)
            expanded_text = _expand_snippets(doc_path.read_text(encoding="utf-8"))
            self.assertIn(
                key_name,
                expanded_text,
                f"Schema v15 key '{key_name}' not found in {doc_rel}",
            )

    def test_inspector_field_labels_match_property_specs(self):
        """Validate Inspector field labels in parameter tables match controller specs."""
        for kind, roles in ROLES_BY_KIND.items():
            for role in roles:
                doc_rel = self.doc_pages_by_key[(kind.value, role.value)]
                doc_path = self._resolve_doc_path(doc_rel)
                expanded_text = _expand_snippets(doc_path.read_text(encoding="utf-8"))

                controller_cls = CONTROLLER_TYPES.get((kind, role))
                specs_by_key = {spec.key: spec for spec in controller_cls.PROPERTY_SPECS}

                tables = _extract_markdown_tables(expanded_text)
                for headers, rows in tables:
                    if len(headers) == 5 and "persisted" in headers[4].lower():
                        for row in rows:
                            field_label = row[0].strip()
                            norm_key = _normalize_key_name(row[4])
                            spec = specs_by_key.get(norm_key)
                            if spec and spec.label:
                                expected_label = spec.label.rstrip(":")
                                self.assertEqual(
                                    field_label.casefold(),
                                    expected_label.casefold(),
                                    f"Field label mismatch in {doc_rel} for key {norm_key}: got '{field_label}', expected '{expected_label}'",
                                )

    def test_snippet_expansion_and_validity(self):
        """Validate all snippet files exist, expand cleanly, and have no broken directives."""
        snippet_files = list(SNIPPETS_DIR.rglob("*.md"))
        self.assertTrue(len(snippet_files) > 0, "No snippet files found in docs/_snippets")

        for snippet_path in snippet_files:
            text = snippet_path.read_text(encoding="utf-8")
            expanded = _expand_snippets(text, base_dir=DOCS_DIR)
            remaining = SNIPPET_LINE_PATTERN.findall(expanded)
            self.assertEqual(
                remaining,
                [],
                f"Unexpanded snippet directive in snippet {snippet_path}: {remaining}",
            )

        for doc_path in DOCS_DIR.rglob("*.md"):
            if "_snippets" in doc_path.parts:
                continue
            text = doc_path.read_text(encoding="utf-8")
            expanded = _expand_snippets(text, base_dir=DOCS_DIR)
            remaining = SNIPPET_LINE_PATTERN.findall(expanded)
            self.assertEqual(
                remaining,
                [],
                f"Unexpanded snippet directive in {doc_path.relative_to(DOCS_DIR)}: {remaining}",
            )

    def test_matplotlib_urls_are_pinned_to_3_9_0_and_listed_at_bottom(self):
        """Validate all Matplotlib URLs pin 3.9.0 and match bottom reference lists."""
        for (kind_str, role_str), doc_rel in self.doc_pages_by_key.items():
            doc_path = self._resolve_doc_path(doc_rel)
            raw_text = doc_path.read_text(encoding="utf-8")
            expanded_text = _expand_snippets(raw_text, base_dir=DOCS_DIR)

            # Check all matplotlib.org links in the entire expanded text pin 3.9.0
            all_mpl_links = re.findall(r'https?://(?:www\.)?matplotlib\.org/[^\s\)\>"\']+', expanded_text)
            for link in all_mpl_links:
                self.assertTrue(
                    link.startswith("https://matplotlib.org/3.9.0/"),
                    f"Unpinned Matplotlib link '{link}' in {doc_rel}",
                )

            # Extract referenced URLs section at bottom
            ref_section_match = re.search(
                r'## Referenced (?:Matplotlib 3\.9\.0 )?URLs\s*\n([\s\S]*?)(?=\n## |\Z)',
                raw_text,
            )

            # Extract inline links from the main content (before reference section)
            main_content = raw_text[:ref_section_match.start()] if ref_section_match else raw_text
            expanded_main = _expand_snippets(main_content, base_dir=DOCS_DIR)
            body_mpl_links = set(re.findall(r'https://matplotlib\.org/3\.9\.0/[^\s\)\>"\']+', expanded_main))

            if body_mpl_links or ref_section_match:
                self.assertIsNotNone(
                    ref_section_match,
                    f"Page {doc_rel} has Matplotlib URLs but lacks a bottom reference section",
                )
                ref_section_text = ref_section_match.group(1)
                bottom_links = set(re.findall(r'https://matplotlib\.org/3\.9\.0/[^\s\)\>"\']+', ref_section_text))

                missing_in_bottom = body_mpl_links - bottom_links
                self.assertEqual(
                    missing_in_bottom,
                    set(),
                    f"URLs in body of {doc_rel} missing from bottom reference section: {missing_in_bottom}",
                )

    def test_navigation_configuration_and_redirects(self):
        """Validate mkdocs.yml navigation, indexes, snippets, and redirects configuration."""
        self.assertTrue(MKDOCS_YML.is_file(), "mkdocs.yml missing")
        content = yaml.load(MKDOCS_YML.read_text(encoding="utf-8"), Loader=_MkDocsYamlLoader)

        features = content.get("theme", {}).get("features", [])
        self.assertIn("navigation.indexes", features)

        markdown_exts = content.get("markdown_extensions", [])
        snippet_ext = next(
            (ext for ext in markdown_exts if isinstance(ext, dict) and "pymdownx.snippets" in ext),
            None,
        )
        self.assertIsNotNone(snippet_ext, "pymdownx.snippets not configured in markdown_extensions")
        snippet_config = snippet_ext["pymdownx.snippets"]
        self.assertIn("docs", snippet_config.get("base_path", []))
        self.assertTrue(snippet_config.get("check_paths", False))

        plugins = content.get("plugins", [])
        redirects_plugin = next(
            (p for p in plugins if isinstance(p, dict) and "redirects" in p),
            None,
        )
        self.assertIsNotNone(redirects_plugin, "redirects plugin not configured in mkdocs.yml")
        redirect_maps = redirects_plugin["redirects"].get("redirect_maps", {})
        self.assertIn("chart-component-parameters.md", redirect_maps)
        self.assertIn("axes-component-parameters.md", redirect_maps)

    def test_profile_doc_mapping_is_complete_without_build_artifacts(self):
        """Keep the 31-profile mapping checked in so Windows CI does not need build/."""
        expected = {
            (kind.value, role.value)
            for kind, roles in ROLES_BY_KIND.items()
            for role in roles
        }
        self.assertEqual(set(PROFILE_DOC_PAGES), expected)
        self.assertEqual(len(PROFILE_DOC_PAGES), 31)
        for doc_rel in PROFILE_DOC_PAGES.values():
            self.assertTrue(
                (DOCS_DIR / doc_rel).is_file(),
                f"Mapped documentation page is missing: {doc_rel}",
            )


if __name__ == "__main__":
    unittest.main()
