# Documentation Site

MyGUI's documentation site is built with MkDocs and the Material theme from the Markdown files under `docs/` and published to GitHub Pages.

## Layout

- `mkdocs.yml` at the repository root is the only site configuration. Its `docs_dir` is `docs/` and its `nav` groups the existing feature documents; document content stays in the Markdown files.
- `docs/index.md` is the site landing page. Creating Charts includes the
  Annotation, Reference Guides, Reference Marks, Colorbar, Pseudocolor, Heatmap, and
  Contour feature pages, Projects and
  Appearance includes Figure Export, Getting Started includes Application
  Settings, Developer Reference documents the
  Controller/Service/Canvas package layout plus the current schema-v19
  property contract and legacy v18, v17, v16, v15, v14, v13, v12, and v10 migration references,
  and Editing Components mirrors the full 31-profile runtime component
  hierarchy.
- Build output goes to `site/`, which is git-ignored and rebuilt by CI.

## Configuration parameters

- `site_name`: `MyGUI`.
- `theme`: Material with light/dark palettes and the features `search.suggest`, `search.highlight`, `content.code.copy`, `content.code.annotate`, `navigation.top`, and `navigation.indexes`.
- `markdown_extensions`: admonition, tables, toc permalinks, pymdownx details/superfences (with a mermaid custom fence)/highlight, and `pymdownx.snippets` (configured with `base_path: [docs]` and `check_paths: true`).
- `plugins`: `search` and `redirects` (configured via `mkdocs-redirects` with explicit redirect maps).
- `nav`: explicit page list grouped into Getting Started (including Application Settings), Working with Data, Creating Charts, Editing Components, Projects and Appearance, Integrations and Configuration, Developer Reference, and Maintenance & QA. UI theme documented on the Settings page is not Matplotlib Figure style.
- `repo_url` / `edit_uri`: link to the GitHub repository and let visitors edit pages on the `master` branch.

## Navigation hierarchy and component tree

The navigation structure under **Editing Components** strictly mirrors the runtime Components Tree and all 31 production Inspector profiles:

1. **Fixed Semantics (14 profiles)**:
   - `Figure` (`editing-components/fixed-semantics/figure.md`)
   - `Axes` (`editing-components/fixed-semantics/axes.md`)
   - `Axes Structure`:
     - `Spine (Left / Right / Top / Bottom)` (`editing-components/fixed-semantics/axes-structure/spine.md`)
     - `Title` (`editing-components/fixed-semantics/axes-structure/title.md`)
     - `Legend` (`editing-components/fixed-semantics/axes-structure/legend.md`)
   - `X Axis` (`editing-components/fixed-semantics/x-axis/index.md`):
     - `Major Ticks` (`editing-components/fixed-semantics/x-axis/major-ticks.md`) -> `Major Tick Labels` (`editing-components/fixed-semantics/x-axis/major-tick-labels.md`)
     - `Minor Ticks` (`editing-components/fixed-semantics/x-axis/minor-ticks.md`) -> `Minor Tick Labels` (`editing-components/fixed-semantics/x-axis/minor-tick-labels.md`)
     - `Major Grid` (`editing-components/fixed-semantics/x-axis/major-grid.md`) documents the single Grid Inspector profile used by both major and minor grid nodes
     - `X Axis Label` (`editing-components/fixed-semantics/x-axis/x-label.md`)
   - `Y Axis` (`editing-components/fixed-semantics/y-axis/index.md`):
     - Shares Major/Minor Ticks, Major/Minor Tick Labels, and the Grid page co-located under `fixed-semantics/x-axis/`.
     - `Y Axis Label` (`editing-components/fixed-semantics/y-axis/y-label.md`)
2. **Charts (9 profiles)**:
   - `Lines` (`editing-components/charts/line.md`)
   - `Function Curves` (`editing-components/charts/function-curve.md`)
   - `Plots` (`editing-components/charts/plot.md`)
   - `Fit Curves` (`editing-components/charts/fit-curve.md`)
   - `Interpolations` (`editing-components/charts/interpolation.md`)
   - `Scatters` (`editing-components/charts/scatter.md`)
   - `Pseudocolor` (`editing-components/charts/pseudocolor.md`)
   - `Heatmaps` (`editing-components/charts/heatmap.md`)
   - `Contours` (`editing-components/charts/contour.md`)
3. **Texts & Annotations (2 profiles)**:
   - `Texts` (`editing-components/elements/text.md`)
   - `Annotations` (`editing-components/elements/annotation.md`)
4. **Insets (2 profiles)**:
   - `Zoom Insets` (`editing-components/elements/in-axes-zoom.md`)
   - `Image Insets` (`editing-components/elements/in-axes-image.md`)
5. **Colorbars & Reference Guides (4 profiles)**:
   - `Colorbars` (`editing-components/elements/colorbar.md`)
   - `Reference Marks` (`editing-components/elements/reflection-positions.md`)
   - `Reference Guides`:
     - `Reference Line` (`editing-components/elements/reference-line.md`)
     - `Reference Band` (`editing-components/elements/reference-band.md`)

Parent container nodes (`Figure`, `Axes`, `X Axis`, `Y Axis`, `Major Ticks`, `Minor Ticks`) utilize `navigation.indexes` so that clicking the container header directly navigates to its index page while simultaneously expanding the section.

## Snippet architecture

Component documentation uses `pymdownx.snippets` to maintain single-source-of-truth modularity across shared Inspector sections and parameter definitions:

- Snippet files are organized under `docs/_snippets/components/` by concern:
  `charts/`, `text/`, `ticks/`, `common/`, `in_axes/`, and `reference_guides/`.
- `pymdownx.snippets` is configured with `base_path: [docs]` and `check_paths: true`, allowing inclusion via syntax such as `--8<-- "_snippets/components/charts/line-appearance.md"`.
- `check_paths: true` guarantees that any missing or invalid snippet path immediately fails the strict MkDocs build during local verification and CI.
- The `_snippets/` directory is deliberately omitted from standalone navigation in `mkdocs.yml` to prevent raw snippet fragments from appearing as independent documentation pages.

## Redirect policy

Monolithic parameter pages from earlier documentation versions are retired and replaced by the granular 31-profile component hierarchy. Backward compatibility for legacy URLs and bookmarks is guaranteed via `mkdocs-redirects` under `plugins`:

- `chart-component-parameters.md` -> `editing-components/charts/line.md`
- `axes-component-parameters.md` -> `editing-components/fixed-semantics/axes.md`

`mkdocs-redirects` automatically generates HTML meta-refresh stubs in the built `site/` output, ensuring external incoming links and bookmarks resolve seamlessly to the new destination pages without broken links.

## External links

- Parameter pages link only to Matplotlib 3.9.0 pages (`https://matplotlib.org/3.9.0/...`) because MyGUI targets that release; do not use `stable` links.
- Inline links live in the Meaning/Description cell of a parameter row. Every row of an uncommon value family (cap/join, hatch, fill style, sketch/snap, rotation mode, and similar) carries its own link so each Inspector control resolves directly; plain single-row parameters link once.
- Every page with inline parameter links keeps its bottom `Matplotlib reference` / `Referenced URLs` list complete, so each referenced URL also appears there.

## Preview and build

With the maintenance dependencies installed (`pip install -r requirements-dev.txt`):

```powershell
python -m mkdocs serve          # local preview with live reload
python -m mkdocs build --strict # build site/; fails on broken links or warnings
```

## Publishing

`.github/workflows/docs.yml` builds the site with `--strict` on every pull request and, on pushes to `master` or a manual `workflow_dispatch` run, deploys it to GitHub Pages through `actions/deploy-pages`. Repository Settings → Pages must use the GitHub Actions source.
