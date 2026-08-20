/**
 * Minimal Python lexical layer for the scanners.
 *
 * The scanners must not depend on a Python interpreter or on heavyweight AST
 * frameworks. This module performs a controlled lexical pass over Python
 * source: it blanks string/comment regions (preserving column positions) and
 * tracks indentation, bracket depth, and logical-statement boundaries. All
 * rule analysis then runs on the blanked code, so strings and comments can
 * never produce false matches.
 */

/** A valid Python string-literal prefix (r/b/u/f and two-letter combos). */
const STRING_PREFIXES = new Set([
  'r', 'b', 'u', 'f',
  'rb', 'br', 'fr', 'rf',
  'R', 'B', 'U', 'F',
  'RB', 'BR', 'FR', 'RF',
  'Rb', 'bR', 'Fr', 'rF',
]);

export interface PyLine {
  /** 1-based line number. */
  number: number;
  /** Raw source text (without the trailing newline). */
  raw: string;
  /** Indentation width of the leading whitespace (tab = 4). */
  indent: number;
  /** Source with string and comment regions replaced by spaces. */
  code: string;
  /** `code` trimmed. */
  trimmed: string;
}

export interface PyTokenizeResult {
  lines: PyLine[];
}

function isIdentStart(ch: string): boolean {
  return /[A-Za-z_]/.test(ch);
}

function isIdentChar(ch: string): boolean {
  return /[A-Za-z0-9_]/.test(ch);
}

/**
 * Scan one physical line and return it with string literals and comments
 * blanked to spaces (positions preserved).
 */
function blankLine(raw: string): string {
  const out: string[] = new Array(raw.length).fill(' ');
  let i = 0;
  const n = raw.length;
  while (i < n) {
    const ch = raw[i]!;
    if (ch === '#') {
      // Comment to end of line.
      break;
    }
    if (ch === "'" || ch === '"') {
      // Detect an optional string prefix immediately before the quote.
      let prefixStart = i;
      while (prefixStart > 0 && isIdentChar(raw[prefixStart - 1]!)) prefixStart -= 1;
      const prefix = raw.slice(prefixStart, i);
      if (prefixStart === i || STRING_PREFIXES.has(prefix)) {
        const triple = raw.slice(i, i + 3) === ch.repeat(3);
        const close = triple ? ch.repeat(3) : ch;
        let j = i + (triple ? 3 : 1);
        let end = -1;
        while (j < n) {
          if (raw[j] === '\\') {
            j += 2;
            continue;
          }
          if (raw.startsWith(close, j)) {
            end = j + close.length;
            break;
          }
          j += 1;
        }
        if (end < 0) {
          // Unterminated string: blank to end of line.
          i = n;
          break;
        }
        for (let k = prefixStart; k < end; k += 1) out[k] = ' ';
        i = end;
        continue;
      }
    }
    out[i] = ch;
    i += 1;
  }
  return out.join('');
}

/** Count the indentation width of a line's leading whitespace (tab = 4). */
function indentWidth(raw: string): number {
  let width = 0;
  for (const ch of raw) {
    if (ch === ' ') width += 1;
    else if (ch === '\t') width += 4;
    else break;
  }
  return width;
}

/** Tokenize one file into per-line records. */
export function tokenize(source: string): PyTokenizeResult {
  const rawLines = source.split(/\r?\n/);
  // Drop a trailing empty element produced by a final newline.
  if (rawLines.length > 0 && rawLines[rawLines.length - 1] === '') rawLines.pop();
  const lines: PyLine[] = rawLines.map((raw, index) => {
    const code = blankLine(raw);
    return {
      number: index + 1,
      raw,
      indent: indentWidth(raw),
      code,
      trimmed: code.trim(),
    };
  });
  return { lines };
}

/** Compute the bracket-depth delta of one blanked line. */
export function bracketDelta(code: string): number {
  let depth = 0;
  for (const ch of code) {
    if (ch === '(' || ch === '[' || ch === '{') depth += 1;
    else if (ch === ')' || ch === ']' || ch === '}') depth -= 1;
  }
  return depth;
}

/** True when the blanked line continues the previous logical statement. */
export function isContinuationLine(line: PyLine, depthBefore: number): boolean {
  if (depthBefore > 0) return true;
  if (line.trimmed === '') return true;
  // Explicit backslash continuation (rare but legal).
  if (line.code.trimEnd().endsWith('\\')) return true;
  return false;
}

/** Return true when a blanked line is pure comment/whitespace. */
export function isBlankLine(line: PyLine): boolean {
  return line.trimmed === '';
}
