# Documentation Site

MyGUI's documentation site is built with MkDocs and the Material theme from the Markdown files under `docs/` and published to GitHub Pages.

## Layout

- `mkdocs.yml` at the repository root is the only site configuration. Its `docs_dir` is `docs/` and its `nav` groups the existing feature documents; document content stays in the Markdown files.
- `docs/index.md` is the site landing page. Creating Charts includes the
  Reference Guides and Reference Marks feature pages, Projects and Appearance
  includes Figure Export, and Developer Reference
  links the current schema-v15 property contract plus the legacy v14, v13, v12, and
  v10 migration references.
- Build output goes to `site/`, which is git-ignored and rebuilt by CI.

## Configuration parameters

- `site_name`: `MyGUI`.
- `theme`: Material with light/dark palettes and the features `search.suggest`, `search.highlight`, `content.code.copy`, `content.code.annotate`, and `navigation.top`.
- `markdown_extensions`: admonition, tables, toc permalinks, and pymdownx details/superfences (with a mermaid custom fence)/highlight.
- `nav`: explicit page list grouped into Getting Started, Working with Data, Creating Charts, Editing Components, Projects and Appearance, Integrations and Configuration, Developer Reference, and Maintenance & QA.
- `repo_url` / `edit_uri`: link to the GitHub repository and let visitors edit pages on the `master` branch.

## External links

- Parameter pages link only to Matplotlib 3.9.0 pages (`https://matplotlib.org/3.9.0/...`) because MyGUI targets that release; do not use `stable` links.
- Inline links live in the Meaning/Description cell of a parameter row. Every row of an uncommon value family (cap/join, hatch, fill style, sketch/snap, rotation mode, and similar) carries its own link so each Inspector control resolves directly; plain single-row parameters link once.
- Every page with inline parameter links keeps its bottom `Matplotlib reference` list complete, so each referenced URL also appears there.

## Preview and build

With the maintenance dependencies installed (`pip install -r requirements-dev.txt`):

```powershell
python -m mkdocs serve          # local preview with live reload
python -m mkdocs build --strict # build site/; fails on broken links or warnings
```

## Publishing

`.github/workflows/docs.yml` builds the site with `--strict` on every pull request and, on pushes to `master` or a manual `workflow_dispatch` run, deploys it to GitHub Pages through `actions/deploy-pages`. Repository Settings → Pages must use the GitHub Actions source.
