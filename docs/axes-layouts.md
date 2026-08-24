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

## FullProf XRD refinement import

The creation dialogs for **Single Axes** and **Main Plot + Residual** include
an **XRD Refinement** tab. Editing an existing layout and the other templates
do not show the tab. Its optional input is a FullProf `.prf` result. Selecting
a file parses and validates it immediately and previews its title, χ², profile
point count, reflection count, and 2θ range. An invalid file is reported inline
and disables **Create**. With **Import XRD refinement result** off, the controls
are disabled and the template follows its ordinary layout-only creation path.

| Dialog field | Control | Meaning | Default | Persisted key |
| --- | --- | --- | --- | --- |
| Import XRD refinement result | Checkbox | Enables the optional FullProf `.prf` workflow. | Off | Transient; not persisted |
| Draw residual | Checkbox | Single Axes only. When on, overlays the original `Yobs-Ycal (PRF)` Plot on the same Axes. | On for Single; hidden for Main + Residual | Transient; applied by creating or omitting the Residual Plot |
| File | Path plus **Browse…** | FullProf profile-result file, filtered as `FullProf PRF (*.prf)` and parsed when selected. | Empty | Transient; the source path is not persisted |
| Observed | Checkbox | Includes the imported Observed Scatter in the legend. Single defaults off; Main + Residual defaults on. | Off (Single) / On (Main + Residual) | Applied through the Scatter `properties.label` and Legend state |
| Calculated | Checkbox | Includes the imported Calculated Data Plot in the legend. Single defaults off; Main + Residual defaults on. | Off (Single) / On (Main + Residual) | Applied through the Data Plot `properties.label` and Legend state |
| Reflection positions | Checkbox | Includes the existing Reflection Positions component in the legend. | Off | Applied through Reference Marks `properties.label` and Legend state |
| Residual | Checkbox | Includes the Residual Data Plot in the legend. Disabled when Single Draw residual is off. | Off | Applied through the Data Plot `properties.label` and Legend state |
| Observed Scatter… | Button | Opens the Scatter marker, size, and color controls. Cancel leaves the request unchanged. | `#D62728` circle, size `1.0` | Applied on create through Scatter properties; not a project field of the dialog |
| Calculated Plot… | Button | Opens the Plot line style, line width, and color controls. Cancel leaves the request unchanged. | `#000000` solid, linewidth `0.5` | Applied on create through Data Plot properties; not a project field of the dialog |
| Reflection Positions… | Button | Opens label, baseline, height, color, and line width. With Single Draw residual on, baseline shows **Automatic** and is disabled; otherwise pre-creation geometry is limited to `baseline + height <= 0.1`. Cancel leaves the request unchanged. | XRD `baseline=0.0375`, `height=0.025`; color/width from the current Figure style | Applied on create through Reference Marks properties; data remains `positions=[]` plus `position_ref` and `placement` |
| Residual Plot… | Button | Opens the residual Plot line style, line width, and color controls. Disabled when Single Draw residual is off. Cancel leaves the request unchanged. | `#0000FF` solid, linewidth `0.2` | Applied on create through Data Plot properties; not a project field of the dialog |

On **Main Plot + Residual** creation, the upper semantic Axes at row 0 receives
an Observed Scatter, a Calculated Data Plot, and the existing Reflection
Positions component bound to `<source> Reflections/2Theta`. That Axes keeps Y
autoscale on and sets `y_lower_reserve=0.1` so ordinary autoscale content
occupies the upper 90% of the Axes. The lower semantic Axes at row 1 receives a
Residual Data Plot bound to the recomputed `Residual = Yobs - Ycal` column and
keeps `y_lower_reserve=0.0`. The offset FullProf difference column is not used
for that line. The two Axes keep the template's shared-X and outer-label
behavior. Main and Residual legends remain independent, and an empty legend
selection hides the corresponding Legend.

On **Single Axes** creation, one Axes receives Observed Scatter, Calculated
Plot, Reflection Positions, and a Chi² Text at Axes coordinates `(0.04, 0.96)`
with the current Figure style font. Missing χ² values display `χ²: —`. **Draw
residual** (default on) adds a Residual Plot bound to `Yobs-Ycal (PRF)` on the
same Axes, sets `y_lower_reserve=0.0`, and places Reflection Positions with
`between_table_ranges` between the PRF difference maximum and the lowest
`Yobs`/`Ycal` values. If that file has no display gap, creation is rejected.
Turning Draw residual off omits the blue line, restores `y_lower_reserve=0.1`,
and uses fixed `baseline=0.0375` / `height=0.025`. Single legend checkboxes all
default off; every selected entry enters the same Axes Legend. The source
`.prf` path is not persisted, and no filename Text is created.

Observed, Calculated, and Residual use the fixed labels `Observed`,
`Calculated`, and `Residual` when their legend checkboxes are on; Reflection
uses the user label, or `Reflection positions` when that checkbox is on and
the label is empty.

The import creates two commands in the project's shared history: **Import XRD
Refinement Data**, followed by **Create XRD Refinement Plot**. Undo therefore
removes the Figure setup before removing its source sheets; Redo restores the
sheets before the data-backed components.

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

Schema v15 stores geometry under the Figure root in `data.layouts`. Each layout contains:

- stable `id`;
- `nrows`, `ncols`;
- `width_ratios`, `height_ratios`;
- `margins.left/right/bottom/top`;
- `spacing.wspace/hspace`.

Each Axes stores `data.subplot` with `layout_id`, zero-based `row` and `column`, `layer` (`primary` or `right_y`), and nullable `share_x_group` / `share_y_group` IDs. Template keys, dialog summaries, expanded groups, XRD import controls, the PRF source path, and other UI state are not persisted.
