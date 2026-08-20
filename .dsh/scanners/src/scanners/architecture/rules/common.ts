/**
 * Shared helpers for architecture rules: chain predicates, receiver
 * classification (artist vs widget), and finding construction.
 */

import { fingerprintFor } from '../../../lib/hash.ts';
import type { AttrChain, ChainSegment, PyFileModel } from '../../../lib/py/model.ts';
import {
  type ScannerFinding,
  ScannerContractError,
  type ScannerDiagnostic,
  type ScannerRequest,
  type ScannerSeverity,
} from '../../../contracts.ts';

export interface RuleRunContext {
  request: ScannerRequest;
  workspace: string;
  /** All scanned file models (test files already excluded by the scanner). */
  files: PyFileModel[];
}

export type { ScannerFinding, ScannerSeverity } from '../../../contracts.ts';

export interface RuleOutcome {
  findings: ScannerFinding[];
  diagnostics: ScannerDiagnostic[];
}

export interface ArchitectureRule {
  id: string;
  description: string;
  run(context: RuleRunContext): RuleOutcome | Promise<RuleOutcome>;
}

/** Names of the private Qt layout containers the rule guards. */
export const PRIVATE_CONTAINER_ATTRS = [
  '_figure_stack',
  '_inspector_stack',
  '_toolboxes',
  '_chart_stack',
  '_element_stack',
] as const;

export function isWidgetsPath(relPath: string): boolean {
  return relPath.startsWith('mygui/widgets/');
}

export function isDomainPath(relPath: string): boolean {
  return relPath.startsWith('mygui/figuremodify/');
}

/** Non-index segment names of a chain, in order. */
export function namedSegments(chain: AttrChain): string[] {
  return chain.segments.filter((segment) => !segment.isIndex).map((segment) => segment.name);
}

/** Last non-index segment name. */
export function lastNamed(chain: AttrChain): string | undefined {
  for (let i = chain.segments.length - 1; i >= 0; i -= 1) {
    const segment = chain.segments[i]!;
    if (!segment.isIndex) return segment.name;
  }
  return undefined;
}

/** First non-index segment name. */
export function firstNamed(chain: AttrChain): string | undefined {
  const first = chain.segments[0]!;
  return first.isIndex ? undefined : first.name;
}

/** True when any non-index segment equals `name`. */
export function hasNamedSegment(chain: AttrChain, name: string): boolean {
  return chain.segments.some((segment) => !segment.isIndex && segment.name === name);
}

/** True when the chain contains `name` followed by a bracket index segment. */
export function hasIndexedSegment(chain: AttrChain, name: string): boolean {
  for (let i = 0; i < chain.segments.length - 1; i += 1) {
    const segment = chain.segments[i]!;
    if (!segment.isIndex && segment.name === name && chain.segments[i + 1]!.isIndex) return true;
  }
  return false;
}

const WIDGET_EXACT = new Set([
  'input', 'editor', 'widget', 'label', 'button', 'btn', 'box', 'panel', 'stack', 'combo',
  'spin', 'slider', 'scroll', 'tab', 'tree', 'table', 'view', 'dialog', 'window', 'layout',
  'menu', 'action', 'icon', 'pixmap', 'cursor', 'frame', 'splitter', 'toolbar', 'statusbar',
  'checkbox', 'radio', 'groupbox', 'field', 'binding', 'edit', 'dropdown', 'delegate',
  'proxy', 'filter', 'dock', 'header', 'footer', 'indicator', 'thumb', 'handle', 'bar',
  'title', 'page', 'card', 'banner', 'tabs', 'tabwidget', 'label_widget',
]);

const WIDGET_SUFFIX =
  /_(input|editor|widget|label|button|btn|box|panel|stack|combo|spin|slider|scroll|tab|tree|table|view|dialog|window|layout|menu|action|icon|pixmap|cursor|frame|splitter|toolbar|statusbar|checkbox|radio|groupbox|field|binding|edit|dropdown|delegate|proxy|filter|dock|header|footer|indicator|thumb|handle|bar|title|page|card|banner|list|item|icon|index|count|name|size|policy|hint|tip|text|tooltip|whatsthis)$/;

const ARTIST_EXACT = new Set([
  'artist', 'artists', 'line', 'lines', 'patch', 'patches', 'collection', 'collections',
  'image', 'images', 'scatter', 'scatters', 'rect', 'rects', 'rectangle', 'rectangles',
  'legend', 'legends', 'annotation', 'annotations', 'gridline', 'gridlines', 'spine',
  'spines', 'tick', 'ticks', 'axline', 'axlines', 'text_artist', 'text_artists',
  'text_artists', 'image_artist', 'bar_container', 'errorbar', 'errorbars', 'contour',
  'contours', 'quiver', 'streamplot', 'artist_handle',
]);

const ARTIST_SUFFIX =
  /_(artist|artists|line|lines|patch|patches|collection|collections|image|images|scatter|scatters|rect|rects|rectangle|legend|annotation|gridline|spine|tick|axline|text_artist|bar_container|errorbar|contour)s?$/;

/** Matplotlib object names: a receiver containing one is matplotlib-owned. */
const MPL_OBJECT_NAMES = new Set(['fig', 'figure', 'ax', 'axes', 'axis']);

/**
 * Heuristic receiver classification. Only strong signals classify a receiver
 * as a Matplotlib artist; everything ambiguous returns false (no report).
 */
export function receiverIsArtistLike(chain: AttrChain, model: PyFileModel): boolean {
  const receiver = chain.segments.slice(0, -1);
  if (receiver.length === 0) return false;

  // Axis/figure-level commands (`ax.set_xlabel(...)`, `fig.set_size_inches(...)`)
  // are the sanctioned axes-command path — never artist mutations.
  const last = lastNamed({ segments: receiver, line: chain.line, startCol: 0, endCol: 0, isCall: false });
  if (last !== undefined && MPL_OBJECT_NAMES.has(last)) return false;

  // A chain rooted in a matplotlib object (fig/ax/axes/axis) is artist-owned.
  if (receiver.some((segment) => !segment.isIndex && MPL_OBJECT_NAMES.has(segment.name))) return true;

  // Widget-name signal: not an artist.
  if (last !== undefined && (WIDGET_EXACT.has(last) || WIDGET_SUFFIX.test(last))) return false;

  // Artist-name signal.
  if (last !== undefined && (ARTIST_EXACT.has(last) || ARTIST_SUFFIX.test(last))) return true;

  // Matplotlib container indexing: `fig.axes[0].lines[0]`, `ax.patches[0]`, ...
  for (const container of ['axes', 'lines', 'patches', 'texts', 'collections', 'images', 'artists']) {
    if (hasIndexedSegment({ ...chain, segments: receiver }, container)) return true;
  }

  // One-level local alias: `artist = self.fig.axes[0].lines[0]` then `artist.set_*`.
  const first = receiver[0]!;
  if (!first.isIndex) {
    const alias = model.aliasLine(first.name, chain.line);
    if (alias !== undefined && receiverIsArtistLike(alias, model)) return true;
  }

  return false;
}

/** Strong widget/domain signal used to separate a gray candidate from a known non-Artist. */
export function receiverIsKnownNonArtist(chain: AttrChain): boolean {
  const receiver = chain.segments.slice(0, -1);
  if (receiver.length === 0) return true;
  const last = lastNamed({ ...chain, segments: receiver });
  if (last === undefined) return false;
  if (WIDGET_EXACT.has(last) || WIDGET_SUFFIX.test(last)) return true;
  return /_(controller|service|coordinator|registry|model|state|repository|manager|factory|context|presenter)$/.test(last)
    || /^(controller|service|coordinator|registry|model|state|repository|manager|factory|context|presenter)$/.test(last);
}

/** Truncated evidence text (brief, per the finding contract). */
export function evidenceOf(model: PyFileModel, line: number, maxLength = 160): string {
  const raw = model.lines[line - 1]?.raw.trim() ?? '';
  if (raw.length <= maxLength) return raw;
  return `${raw.slice(0, maxLength - 1)}…`;
}

/** Build a finding with stable fingerprint and id. */
export function makeFinding(options: {
  model: PyFileModel;
  ruleId: string;
  line: number;
  severity: ScannerSeverity;
  confidence: number;
  title: string;
  reason: string;
  suggestedAction?: string;
  tags?: string[];
}): ScannerFinding {
  const { model, ruleId, line, severity, confidence, title, reason, suggestedAction, tags } = options;
  const evidence = evidenceOf(model, line);
  const id = `${ruleId}@${model.path}#${line}`;
  return {
    id,
    scannerId: 'mygui.architecture',
    ruleId,
    severity,
    confidence,
    file: model.path,
    line,
    title,
    evidence,
    reason,
    suggestedAction: suggestedAction ?? 'Route the operation through the authoritative Controller or Service and add a regression test.',
    tags: tags ?? [],
    fingerprint: fingerprintFor(ruleId, model.path, line, evidence),
  };
}

/** Assert the model path is workspace-relative (contract guard). */
export function assertRelativePath(path: string): void {
  if (path.startsWith('/') || /^[A-Za-z]:[\\/]/.test(path) || path.startsWith('..')) {
    throw new ScannerContractError(`file ${JSON.stringify(path)} must be workspace-relative`);
  }
}
