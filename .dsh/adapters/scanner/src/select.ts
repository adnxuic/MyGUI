/**
 * Scanner selection policy for the Scanner Worker.
 *
 * Selection NEVER guesses capability from a scanner id. It works from the
 * registry's metadata (`id`, `version`, `description`) and the task text:
 *
 *   1. If the caller supplied `requestedScanners`, validate those ids
 *      against the registry — unknown ids are reported, not silently
 *      dropped.
 *   2. Otherwise score every registered scanner against the task text by
 *      token overlap with its metadata, and return the matching ids in
 *      deterministic (registry) order.
 *   3. No match -> empty selection, which the Worker reports as
 *      `missing_capability` instead of inventing an ad-hoc scan.
 */

export interface ScannerMetadata {
  id: string;
  version: string;
  description: string;
}

const TOKEN_RE = /[a-z0-9][a-z0-9-]*/g;

/** Lowercased token set of a text. */
function tokenize(text: string): Set<string> {
  const tokens = new Set<string>();
  for (const match of String(text).toLowerCase().matchAll(TOKEN_RE)) {
    tokens.add(match[0]);
  }
  return tokens;
}

/** Words that only express the request, not a capability need. */
const STOP_WORDS = new Set([
  'the', 'a', 'an', 'for', 'of', 'to', 'in', 'on', 'and', 'or', 'not',
  'check', 'scan', 'scanner', 'scanning', 'run', 'running', 'mygui', 'my',
  'this', 'that', 'with', 'against', 'repository', 'repo', 'workspace',
  'files', 'file', 'code', 'please', 'detection', 'only', 'do', 'does',
  'documented', 'documentation', 'violations', 'violation', 'boundaries',
]);

/**
 * Score one scanner's metadata against the task text: number of shared
 * meaningful tokens (id + version + description vs task).
 */
export function scoreScanner(metadata: ScannerMetadata, task: string): number {
  const taskTokens = tokenize(task);
  const metaTokens = tokenize(`${metadata.id} ${metadata.version} ${metadata.description}`);
  let score = 0;
  for (const token of taskTokens) {
    if (STOP_WORDS.has(token)) continue;
    if (metaTokens.has(token)) score += 1;
  }
  return score;
}

/** Selection outcome: chosen scanner ids plus any unknown requested ids. */
export interface ScannerSelection {
  selected: string[];
  /** Requested ids that are not in the registry. */
  unknownRequested: string[];
}

/**
 * Select scanners for a task.
 *
 * @param registry   live metadata from `myguiScanners.list()` (or the
 *                   equivalent test double)
 * @param task       the inspection task text
 * @param requested  optional explicit scanner ids
 * @param max        maximum number of scanners to select (first version
 *                   runs them sequentially; no parallelism)
 */
export function selectScanners(
  registry: readonly ScannerMetadata[],
  task: string,
  requested?: readonly string[],
  max = 8,
): ScannerSelection {
  const known = new Set(registry.map((entry) => entry.id));

  if (requested !== undefined && requested.length > 0) {
    const selected: string[] = [];
    const unknownRequested: string[] = [];
    for (const id of requested) {
      if (known.has(id)) {
        if (!selected.includes(id)) selected.push(id);
      } else {
        unknownRequested.push(id);
      }
    }
    return { selected, unknownRequested };
  }

  const scored = registry
    .map((entry) => ({ entry, score: scoreScanner(entry, task) }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => {
      // Deterministic: score desc, then registry id asc.
      if (b.score !== a.score) return b.score - a.score;
      return a.entry.id < b.entry.id ? -1 : a.entry.id > b.entry.id ? 1 : 0;
    });

  return {
    selected: scored.slice(0, max).map(({ entry }) => entry.id),
    unknownRequested: [],
  };
}
