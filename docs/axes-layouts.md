# Axes Layout Templates

The Layout command creates a complete scientific Axes arrangement from one of seven fixed templates. The selected template creates all primary and right-Y Axes, fixed semantic component trees, sharing links, Inspectors, and persisted layout state in one transaction.

## Templates

| Template | Structure | Sharing |
|---|---|---|
| **Single Axes** | One 1 × 1 primary Axes | Independent |
| **Horizontal Comparison** | Two primary Axes in a 1 × 2 row | Shared Y by default; the dialog switch can make them independent |
| **Vertical Stack** | Two primary Axes in a 2 × 1 column | Shared X by default; the dialog switch can make them independent |
| **2 × 2 Grid** | Four primary Axes filling a 2 × 2 grid | Independent |
| **3 × 3 Grid** | Nine primary Axes filling a 3 × 3 grid | Independent |
| **Primary + Right Y** | One primary Axes and one `twinx()` right-Y Axes | X is shared by the twin pair |
| **Main Plot + Residual** | Two primary Axes in a 2 × 1 column with a 3:1 default height ratio | Shared X |

Horizontal Comparison exposes only **Share Y axis**. When it is disabled, both Y-axis label sets remain visible. Vertical Stack similarly exposes only **Share X axis**. Disabling it restores both X-axis label sets. The Main Plot + Residual relationship is fixed and keeps labels only on the bottom X axis.

The title bar is the authoritative template selector. The dialog displays the selected icon, name, dimensions, and sharing summary; it does not expose a second template selector, arbitrary row/column controls, or cell-occupancy controls.

## Advanced geometry

Advanced geometry is collapsed by default during creation and expanded while editing an existing layout.

- `width_ratios`: comma-separated positive column width ratios. The value count must equal the template's fixed column count.
- `height_ratios`: comma-separated positive row height ratios. The value count must equal the template's fixed row count.
- `left`, `right`, `bottom`, `top`: normalized Figure margins. They require `0 <= left < right <= 1` and `0 <= bottom < top <= 1`.
- `wspace`, `hspace`: non-negative horizontal and vertical GridSpec spacing values.
- `constrained_layout`: applies Matplotlib constrained layout to the Figure.

Invalid geometry is reported inline and disables Create or Apply. Editing geometry preserves existing Axes artists, component IDs, occupied cells, sharing groups, and twin relationships.

## Common Axes parameters

The Axes tab applies creation values to every primary Axes in the selected template:

- automatic or explicit X/Y limits;
- `linear`, `log`, `symlog`, or `logit` scales;
- X/Y inversion;
- `auto` or `equal` aspect;
- optional style-background override through the shared `ColorChoiceWidget` and application `ColorLibrary`;
- independent X/Y major and minor grid visibility.

Only Primary + Right Y displays right-Y creation controls. They provide automatic or explicit Y range, Y scale, and inversion. The right-Y X state is inherited from the primary Axes.

## Twin legends and deletion

Primary + Right Y can merge entries from both Axes into the primary legend. The setting persists as `Legend.properties.entry_scope` with value `axes` or `twin_pair`.

Deleting a right-Y Axes leaves its primary Axes in place and resets a merged primary Legend to independent entries. Deleting a primary Axes includes its right-Y Axes in the same deletion transaction. If deletion leaves only one member of a sharing group, that survivor becomes independent. An unused Figure layout definition is removed with the final Axes that references it.

## Project records

Schema v11 stores geometry under the Figure root in `data.layouts`. Each layout contains:

- stable `id`;
- `nrows`, `ncols`;
- `width_ratios`, `height_ratios`;
- `margins.left/right/bottom/top`;
- `spacing.wspace/hspace`.

Each Axes stores `data.subplot` with `layout_id`, zero-based `row` and `column`, `layer` (`primary` or `right_y`), and nullable `share_x_group` / `share_y_group` IDs. Template keys, dialog summaries, expanded groups, and other UI state are not persisted.
