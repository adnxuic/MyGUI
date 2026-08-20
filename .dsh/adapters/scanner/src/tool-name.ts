/**
 * Deterministic `scannerId -> toolName` mapping for dynamic Scanner
 * Adapters.
 *
 * Rule: take the scanner id, lowercase it, replace every character that is
 * not `[a-z0-9]` with `_`, collapse runs of `_`, trim leading/trailing `_`,
 * then append the fixed `_scan` suffix.
 *
 *   mygui.architecture  -> mygui_architecture_scan
 *   mygui.qt-lifecycle  -> mygui_qt_lifecycle_scan
 *   MyGUI.Qt-Lifecycle  -> mygui_qt_lifecycle_scan
 *
 * The mapping is deterministic, stable, collision-free within one registry,
 * and yields legal model-facing tool names (`^[a-z][a-z0-9_]*$`).
 */

const TOOL_NAME_RE = /^[a-z][a-z0-9_]*$/;

/**
 * Derive the deterministic model-facing tool name for a scanner id.
 * Throws when the scanner id is empty or cannot yield a legal tool name.
 */
export function toolNameFor(scannerId: string): string {
  if (typeof scannerId !== 'string' || scannerId === '') {
    throw new Error(`scannerId must be a non-empty string, got ${JSON.stringify(scannerId)}`);
  }
  const normalized = scannerId
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  if (normalized === '') {
    throw new Error(`scannerId ${JSON.stringify(scannerId)} cannot be mapped to a tool name`);
  }
  const toolName = `${normalized}_scan`;
  if (!TOOL_NAME_RE.test(toolName)) {
    throw new Error(`scannerId ${JSON.stringify(scannerId)} maps to illegal tool name ${JSON.stringify(toolName)}`);
  }
  return toolName;
}

/**
 * Detect collisions between two distinct scanner ids that would map to the
 * same tool name (e.g. `mygui.qt-lifecycle` vs `mygui.qt_lifecycle`).
 * Returns a map toolName -> [scannerIds...] for every collision found.
 */
export function findToolNameCollisions(scannerIds: readonly string[]): Record<string, string[]> {
  const byToolName = new Map<string, string[]>();
  for (const scannerId of scannerIds) {
    const toolName = toolNameFor(scannerId);
    const bucket = byToolName.get(toolName) ?? [];
    bucket.push(scannerId);
    byToolName.set(toolName, bucket);
  }
  const collisions: Record<string, string[]> = {};
  for (const [toolName, ids] of byToolName) {
    if (ids.length > 1) collisions[toolName] = ids;
  }
  return collisions;
}

/** Validate that a tool name is legal for the model-facing tool registry. */
export function isLegalToolName(toolName: string): boolean {
  return TOOL_NAME_RE.test(toolName);
}
