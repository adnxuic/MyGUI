# Annotation Component

Annotation adds a persistent semantic label to an ordinary Axes. It combines
text, a pointed target (`xy`), an independently positioned text anchor
(`xytext`), and an optional arrow. The resulting component participates in the
Components tree, Inspector, duplication, deletion, project save/open,
templates, and project Undo/Redo.

## Create an Annotation

Use either workflow:

- Choose **Elements > Annotation**. Enter the text, target coordinate system
  and X/Y values, text coordinate system and X/Y values, and whether to show
  the arrow.
- Right-click a finite data position inside a registered ordinary Axes and
  choose **Add Annotation Here**. MyGUI creates `New Annotation` with a Data
  target and a `(+20, +20)` point text offset, selects it, opens its Inspector,
  and focuses the Content text editor.

Creation requires an ordinary Axes. The canvas menu does not open over
Colorbar or In-Axes auxiliary Axes, outside an Axes, or while Pan/Zoom is
active.

Interactive creation resolves typography from the Figure's Text style and
arrow width from its Line style. Arrow color follows text color. Annotation
does not read application Components defaults or advance the Axes chart-color
sequence.

## Coordinate behavior

The target supports:

- **Data**: values follow the Axes data transform, including logarithmic and
  inverted axes.
- **Axes fraction**: `(0, 0)` is the lower-left and `(1, 1)` is the upper-right
  of the Axes.

The text position supports those systems plus **Offset points**. Offset points
measures the text anchor from the target in physical points, so the visual gap
remains stable while the plot is resized or zoomed.

Changing only a coordinate-system selector converts and commits the paired
coordinate value in the same transaction, preserving the on-screen location.
If a coordinate system and coordinate are submitted together, the submitted
coordinate wins. The eight one-shot placement presets write Offset points and
one of the fixed `(0, ±20)`, `(±20, 0)`, or `(±20, ±20)` offsets.

## Tree and lifecycle

Every ordinary Axes has an **Annotations** group. An Annotation uses its
non-empty Name as the tree preview; otherwise it uses whitespace-collapsed
Text. Long previews are shortened to at most 32 characters including the
ellipsis.

Right-click an Annotation to duplicate or delete it. Duplication creates a new
stable ID and the next Annotation sibling order while preserving all semantic
properties. The duplicate initially overlaps the original. Deletion uses the
same atomic deletion coordinator as other removable components.

## Text and Reference Guide boundaries

Use [Text Element](text-element.md) for an unanchored panel label or note. Text
has one position and no pointed target. Use Annotation when the text refers to
a position or feature.

Use [Reference Guides](reference-guides-component.md) for constant lines and
bands. A transition line plus label is represented by two composable
components: a Reference Guide owns geometry and Annotation owns the semantic
label.

## Inspector and persistence

The Inspector exposes Content, Target, Text Position, Arrow, Text Style,
Rotation and alignment, Box, and Advanced sections. See the complete
[Annotation Inspector parameter reference](editing-components/elements/annotation.md).

Schema v17 stores the complete semantic state and reconstructs the Matplotlib
Annotation and arrow patch during restore. Runtime Artists, transforms,
callbacks, widgets, tree groups, and selection are never serialized.

## Referenced Matplotlib 3.9.0 URLs

- [Annotation API](https://matplotlib.org/3.9.0/api/text_api.html#matplotlib.text.Annotation)
- [Axes.annotate](https://matplotlib.org/3.9.0/api/_as_gen/matplotlib.axes.Axes.annotate.html)
- [Annotations guide](https://matplotlib.org/3.9.0/users/explain/text/annotations.html)
