/**
 * Python file model built on top of the tokenizer: logical statements, class
 * and function scopes, attribute chains, and simple per-function alias
 * tracking. This is the analysis surface the architecture rules consume.
 */

import { bracketDelta, isBlankLine, isContinuationLine, tokenize, type PyLine } from './tokenizer.ts';

export type PyScopeKind = 'module' | 'class' | 'def';

export interface PyScope {
  kind: PyScopeKind;
  name: string;
  /** Base class names (class scopes only). */
  bases: string[];
  /** 1-based first line of the scope body. */
  startLine: number;
  /** 1-based last line of the scope body. */
  endLine: number;
  indent: number;
}

export interface PyClassInfo {
  name: string;
  bases: string[];
  startLine: number;
  endLine: number;
  /** Names of methods declared directly in this class body. */
  methods: string[];
}

export interface ChainSegment {
  /** Identifier name; empty for bracket index segments. */
  name: string;
  isIndex: boolean;
  /** 1-based start column of the segment. */
  col: number;
}

/** One dotted attribute chain (with optional bracket segments). */
export interface AttrChain {
  segments: ChainSegment[];
  /** 1-based line. */
  line: number;
  /** 1-based start column. */
  startCol: number;
  /** 1-based end column (exclusive). */
  endCol: number;
  /** True when the chain is immediately followed by a call `(`. */
  isCall: boolean;
}

/** `name = <chain>` recorded from a simple single-line assignment. */
export interface PyAssignment {
  name: string;
  /** The value chain when the RHS is a plain chain, otherwise undefined. */
  valueChain?: AttrChain;
  line: number;
}

/** `self.<attr> = ...` recorded from a simple single-line assignment. */
export interface PySelfAssignment {
  attr: string;
  line: number;
}

/** One import binding: `import matplotlib as mpl`, `from matplotlib import rcParams`. */
export interface PyImportBinding {
  /** Local name the binding introduces (`mpl`, `rcParams`, `matplotlib`). */
  name: string;
  /** Imported module, dotted (`matplotlib`, `matplotlib.pyplot`). */
  module: string;
  /** Imported symbol for `from x import y` bindings, otherwise undefined. */
  symbol?: string;
  /** 1-based line of the import statement. */
  line: number;
  /** Function-local scope range; module-level imports bind file-wide. */
  scopeName?: string;
  scopeStart?: number;
  scopeEnd?: number;
}

export interface PyStatement {
  startLine: number;
  endLine: number;
  /** Statement kind derived from its first line. */
  kind: 'class' | 'def' | 'assign' | 'other';
  /** Trimmed first line (blanked code). */
  header: string;
  indent: number;
}

export interface PyFileModel {
  /** Workspace-relative path (forward slashes). */
  path: string;
  lines: PyLine[];
  /** All attribute chains, ordered by (line, startCol). */
  chains: AttrChain[];
  /** All classes with their bodies. */
  classes: PyClassInfo[];
  /** Innermost scope containing a line, or the module scope. */
  scopeAt(line: number): PyScope;
  /** Innermost class containing a line, if any. */
  classAt(line: number): PyClassInfo | undefined;
  /** Innermost def containing a line, if any. */
  defAt(line: number): { name: string; startLine: number; endLine: number } | undefined;
  assignments: PyAssignment[];
  /** `self.<attr> = ...` assignments (container owner detection). */
  selfAssigns: PySelfAssignment[];
  /** Attribute chains used as assignment targets (`a.b = ...`, `a.b[0] = ...`). */
  assignmentTargetChains: AttrChain[];
  /**
   * One-level local alias lookup: `aliasLine(name, line)` returns the value
   * chain a simple assignment bound to `name` before `line` in the enclosing
   * function, when one exists.
   */
  aliasLine(name: string, line: number): AttrChain | undefined;
  /** Import bindings in declaration order (module- and function-level). */
  importBindings: PyImportBinding[];
  /**
   * Resolve the import binding visible at `line` for a local `name`: the
   * binding introduced by the last import (before `line`) whose scope covers
   * `line`. Returns undefined when `name` is not an imported module or
   * symbol.
   */
  resolveImport(name: string, line: number): { module: string; symbol?: string } | undefined;
}

interface ScopeStackEntry extends PyScope {
  parent: ScopeStackEntry | null;
}

const HEADER_CLASS = /^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\((.*?)\))?\s*:.*$/;
const HEADER_DEF = /^(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(.*$/;

/** Extract base names from a class header's parenthesized part. */
function parseBases(basesText: string | undefined): string[] {
  if (basesText === undefined || basesText.trim() === '') return [];
  return basesText
    .split(',')
    .map((part) => part.trim().split('.')[0] ?? '')
    .filter((name) => name !== '' && /^[A-Za-z_][A-Za-z0-9_]*$/.test(name));
}

function parseHeader(kind: 'class' | 'def', header: string): string {
  const re = kind === 'class' ? HEADER_CLASS : HEADER_DEF;
  const match = re.exec(header);
  return match?.[1] ?? '';
}

/** True when a statement header is a simple assignment (`x = ...`). */
function isSimpleAssignmentHeader(header: string): boolean {
  const eq = header.indexOf('=');
  if (eq <= 0) return false;
  const before = header[eq - 1]!;
  if ('=!<>+-*/%&|^'.includes(before)) return false;
  const after = header[eq + 1];
  if (after === '=') return false;
  // Target: identifier with optional dotted attributes and bracket indices,
  // e.g. `x`, `a.b`, `controller.state.properties["visible"]`.
  const target = header.slice(0, eq).trim();
  if (!/^[A-Za-z_][A-Za-z0-9_.]*$/.test(target.replace(/\[[^\]]*\]/g, ''))) return false;
  return /^[A-Za-z_]/.test(target);
}

/**
 * Build logical statements: consecutive lines that belong together (bracket
 * continuation) are grouped, and each statement is classified.
 */
function buildStatements(lines: PyLine[]): PyStatement[] {
  const statements: PyStatement[] = [];
  let depth = 0;
  let start: PyLine | undefined;
  let end = 0;
  let indent = 0;
  let header = '';

  const flush = (): void => {
    if (start === undefined) return;
    let kind: PyStatement['kind'] = 'other';
    if (HEADER_CLASS.test(header)) kind = 'class';
    else if (HEADER_DEF.test(header)) kind = 'def';
    else if (isSimpleAssignmentHeader(header)) kind = 'assign';
    statements.push({ startLine: start.number, endLine: end, kind, header, indent });
    start = undefined;
  };

  for (const line of lines) {
    const delta = bracketDelta(line.code);
    const continuing = isContinuationLine(line, depth);
    depth += delta;
    if (depth < 0) depth = 0;
    if (start === undefined) {
      if (!isBlankLine(line) && !continuing) {
        start = line;
        end = line.number;
        indent = line.indent;
        header = line.trimmed;
      }
    } else {
      end = line.number;
      if (!header && !isBlankLine(line)) header = line.trimmed;
    }
    if (start !== undefined && depth === 0 && !line.code.trimEnd().endsWith('\\')) {
      flush();
    }
  }
  flush();
  return statements;
}

/** Build the indentation-based scope tree from statements. */
function buildScopes(statements: PyStatement[], totalLines: number): ScopeStackEntry[] {
  const moduleScope: ScopeStackEntry = {
    kind: 'module',
    name: '<module>',
    bases: [],
    startLine: 1,
    endLine: totalLines,
    indent: -1,
    parent: null,
  };
  const scopes: ScopeStackEntry[] = [moduleScope];
  // Every scope ever created (including ones popped off the stack), in
  // creation order; this is what callers consume.
  const allScopes: ScopeStackEntry[] = [moduleScope];

  const popTo = (indent: number, closingLine: number): void => {
    while (scopes.length > 1 && scopes[scopes.length - 1]!.indent >= indent) {
      const top = scopes.pop()!;
      top.endLine = Math.max(top.startLine, closingLine - 1);
    }
  };

  for (const stmt of statements) {
    if (stmt.kind !== 'class' && stmt.kind !== 'def') continue;
    popTo(stmt.indent, stmt.startLine);
    const name = parseHeader(stmt.kind, stmt.header);
    const bases = stmt.kind === 'class' ? parseBases(HEADER_CLASS.exec(stmt.header)?.[2]) : [];
    const parent = scopes[scopes.length - 1]!;
    const scope: ScopeStackEntry = {
      kind: stmt.kind,
      name,
      bases,
      startLine: stmt.startLine,
      endLine: totalLines,
      indent: stmt.indent,
      parent,
    };
    scopes.push(scope);
    allScopes.push(scope);
  }
  // Close every remaining scope at EOF; they stay in `allScopes`.
  popTo(0, totalLines + 1);
  return allScopes;
}

/** Extract attribute chains from one blanked line. */
function extractChains(line: PyLine): AttrChain[] {
  const chains: AttrChain[] = [];
  const code = line.code;
  const n = code.length;
  let i = 0;

  while (i < n) {
    const ch = code[i]!;
    if (!/[A-Za-z_]/.test(ch)) {
      i += 1;
      continue;
    }
    // Consume the leading identifier.
    let j = i;
    while (j < n && /[A-Za-z0-9_]/.test(code[j]!)) j += 1;
    const segments: ChainSegment[] = [
      { name: code.slice(i, j), isIndex: false, col: i + 1 },
    ];
    let k = j;
    let sawAttribute = false;
    // Walk dotted attributes and bracket indices.
    for (;;) {
      let s = k;
      while (s < n && (code[s] === ' ' || code[s] === '\t')) s += 1;
      if (s < n && code[s] === '.') {
        let t = s + 1;
        while (t < n && (code[t] === ' ' || code[t] === '\t')) t += 1;
        if (t < n && /[A-Za-z_]/.test(code[t]!)) {
          let u = t;
          while (u < n && /[A-Za-z0-9_]/.test(code[u]!)) u += 1;
          segments.push({ name: code.slice(t, u), isIndex: false, col: t + 1 });
          sawAttribute = true;
          k = u;
          continue;
        }
      } else if (s < n && code[s] === '[') {
        // Balanced bracket index: strings were blanked, so scan is safe.
        let depth = 1;
        let t = s + 1;
        while (t < n && depth > 0) {
          const c = code[t]!;
          if (c === '[') depth += 1;
          else if (c === ']') depth -= 1;
          t += 1;
        }
        segments.push({ name: '', isIndex: true, col: s + 1 });
        sawAttribute = true;
        k = t;
        continue;
      }
      break;
    }
    let isCall = false;
    {
      let s = k;
      while (s < n && (code[s] === ' ' || code[s] === '\t')) s += 1;
      isCall = s < n && code[s] === '(';
    }
    if (segments.length >= 2 || sawAttribute || isCall) {
      chains.push({
        segments,
        line: line.number,
        startCol: i + 1,
        // 1-based exclusive end: k is the 0-based index of the first
        // unconsumed character, so the exclusive 1-based column is k + 1.
        endCol: k + 1,
        isCall,
      });
    }
    i = k;
  }
  return chains;
}

/** Extract simple single-line assignment targets: `name = <chain>` / `self.x = ...`. */
function extractAssignments(
  model: PyFileModel,
  statements: PyStatement[],
): { assignments: PyAssignment[]; selfAssigns: PySelfAssignment[]; assignmentTargetChains: AttrChain[] } {
  const assignments: PyAssignment[] = [];
  const selfAssigns: PySelfAssignment[] = [];
  const assignmentTargetChains: AttrChain[] = [];
  const lineByNumber = new Map(model.lines.map((line) => [line.number, line]));
  for (const stmt of statements) {
    if (stmt.kind !== 'assign' || stmt.startLine !== stmt.endLine) continue;
    const line = lineByNumber.get(stmt.startLine);
    if (line === undefined) continue;
    const wsLen = line.code.length - line.code.trimStart().length;
    const code = line.code.slice(wsLen);
    const eq = findTopLevelEquals(code);
    if (eq < 0) continue;
    const target = code.slice(0, eq).trim();
    const valueRaw = code.slice(eq + 1);
    const value = valueRaw.trim();
    const valueLead = valueRaw.length - valueRaw.trimStart().length;
    const targetMatch = /^([A-Za-z_][A-Za-z0-9_]*)$/.exec(target);
    if (targetMatch) {
      const name = targetMatch[1]!;
      let valueChain: AttrChain | undefined;
      // The RHS is a plain chain when a chain starts exactly at the value and
      // ends exactly at the end of the statement text.
      const valueStartCol = wsLen + eq + 1 + valueLead + 1;
      const valueEndCol = valueStartCol + value.length;
      const chain = model.chains.find(
        (c) =>
          c.line === line.number &&
          c.startCol === valueStartCol &&
          c.endCol === valueEndCol &&
          !c.isCall &&
          c.segments.length >= 2,
      );
      if (chain !== undefined) valueChain = chain;
      assignments.push({ name, valueChain, line: line.number });
      continue;
    }
    // Attribute-target assignment: `self.x = ...` / `obj.x = ...` / `a.b[0] = ...`.
    const targetChain = model.chains.find(
      (c) =>
        c.line === line.number &&
        c.startCol === wsLen + 1 &&
        c.endCol === wsLen + 1 + target.length &&
        !c.isCall,
    );
    if (targetChain !== undefined && targetChain.segments.length >= 2) {
      assignmentTargetChains.push(targetChain);
      const first = targetChain.segments[0]!;
      const second = targetChain.segments[1]!;
      if (first.name === 'self' && !second.isIndex) {
        selfAssigns.push({ attr: second.name, line: line.number });
      }
    }
  }
  return { assignments, selfAssigns, assignmentTargetChains };
}

/** Find the first `=` at bracket depth 0 that is not a comparison/operator. */
function findTopLevelEquals(code: string): number {
  let depth = 0;
  for (let i = 0; i < code.length; i += 1) {
    const ch = code[i]!;
    if (ch === '(' || ch === '[' || ch === '{') depth += 1;
    else if (ch === ')' || ch === ']' || ch === '}') depth -= 1;
    else if (ch === '=' && depth === 0) {
      const prev = i > 0 ? code[i - 1]! : '';
      const next = i + 1 < code.length ? code[i + 1]! : '';
      if (prev === '=' || prev === '!' || prev === '<' || prev === '>' || next === '=') continue;
      return i;
    }
  }
  return -1;
}

const IMPORT_STATEMENT_RE = /^import\s+(.+)$/;
const FROM_IMPORT_STATEMENT_RE = /^from\s+([A-Za-z_][A-Za-z0-9_.]*)\s+import\s+(.+)$/;
const IMPORT_ITEM_RE = /^([A-Za-z_][A-Za-z0-9_.]*)(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?$/;

function isIdentifier(name: string): boolean {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(name);
}

/**
 * Extract import bindings from single-line import statements:
 * `import matplotlib`, `import matplotlib as mpl`,
 * `from matplotlib import rcParams`, `from matplotlib import rc as rc_fn`.
 * Function-local imports are scoped to their def body; module-level (and
 * class-level) imports bind file-wide. Parenthesized multi-line imports are
 * intentionally not parsed (fail-safe: no binding, no match).
 */
function extractImports(model: PyFileModel, statements: PyStatement[]): PyImportBinding[] {
  const bindings: PyImportBinding[] = [];
  for (const stmt of statements) {
    if (stmt.kind !== 'other' || stmt.startLine !== stmt.endLine) continue;
    const line = model.lines[stmt.startLine - 1];
    if (line === undefined) continue;
    const code = line.trimmed;
    if (!code.startsWith('import ') && !code.startsWith('from ')) continue;
    const scope = model.scopeAt(stmt.startLine);
    const scopeName = scope.kind === 'def' ? scope.name : undefined;
    const scopeStart = scope.kind === 'def' ? scope.startLine : undefined;
    const scopeEnd = scope.kind === 'def' ? scope.endLine : undefined;

    const importMatch = IMPORT_STATEMENT_RE.exec(code);
    if (importMatch) {
      for (const part of importMatch[1]!.split(',')) {
        const item = IMPORT_ITEM_RE.exec(part.trim());
        if (item === null) continue;
        const module = item[1]!;
        const name = item[2] ?? module.split('.')[0]!;
        if (!isIdentifier(name)) continue;
        bindings.push({ name, module, line: stmt.startLine, scopeName, scopeStart, scopeEnd });
      }
      continue;
    }

    const fromMatch = FROM_IMPORT_STATEMENT_RE.exec(code);
    if (fromMatch) {
      const module = fromMatch[1]!;
      let symbols = fromMatch[2]!.trim();
      if (symbols.startsWith('(') && symbols.endsWith(')')) symbols = symbols.slice(1, -1).trim();
      for (const part of symbols.split(',')) {
        const item = part.trim();
        if (item === '' || item === '*') continue;
        const alias = IMPORT_ITEM_RE.exec(item);
        if (alias === null) continue;
        const symbol = alias[1]!;
        const name = alias[2] ?? symbol;
        if (!isIdentifier(name)) continue;
        bindings.push({ name, module, symbol, line: stmt.startLine, scopeName, scopeStart, scopeEnd });
      }
    }
  }
  return bindings;
}

/** Build the full analysis model for one Python file. */
export function buildPyFileModel(path: string, source: string): PyFileModel {
  const { lines } = tokenize(source);
  const statements = buildStatements(lines);
  const scopes = buildScopes(statements, lines.length);

  const chains: AttrChain[] = [];
  for (const line of lines) chains.push(...extractChains(line));

  const model: PyFileModel = {
    path,
    lines,
    chains,
    classes: [],
    assignments: [],
    selfAssigns: [],
    assignmentTargetChains: [],
    importBindings: [],
    scopeAt(line) {
      for (let i = scopes.length - 1; i >= 0; i -= 1) {
        const scope = scopes[i]!;
        if (scope.kind !== 'module' && line >= scope.startLine && line <= scope.endLine) return scope;
      }
      return scopes[0]!;
    },
    classAt(line) {
      const scope = model.scopeAt(line);
      if (scope.kind === 'class') return model.classes.find((c) => c.name === scope.name && c.startLine === scope.startLine);
      if (scope.kind === 'def') {
        let parent = (scope as ScopeStackEntry).parent;
        while (parent !== null && parent.kind === 'def') parent = parent.parent;
        if (parent !== null && parent.kind === 'class') {
          return model.classes.find((c) => c.name === parent.name && c.startLine === parent.startLine);
        }
      }
      return undefined;
    },
    defAt(line) {
      const scope = model.scopeAt(line);
      if (scope.kind === 'def') return { name: scope.name, startLine: scope.startLine, endLine: scope.endLine };
      return undefined;
    },
    aliasLine(name, line) {
      const def = model.defAt(line);
      let best: AttrChain | undefined;
      for (const assignment of model.assignments) {
        if (assignment.name !== name || assignment.valueChain === undefined) continue;
        if (assignment.line >= line) continue;
        if (def !== undefined && (assignment.line < def.startLine || assignment.line > def.endLine)) continue;
        if (best === undefined || assignment.line > best.line) best = assignment.valueChain;
      }
      return best;
    },
    resolveImport(name, line) {
      let best: PyImportBinding | undefined;
      for (const binding of model.importBindings) {
        if (binding.name !== name) continue;
        if (binding.line >= line) continue;
        if (binding.scopeName !== undefined) {
          if (binding.scopeStart === undefined || binding.scopeEnd === undefined) continue;
          if (line < binding.scopeStart || line > binding.scopeEnd) continue;
        }
        if (best === undefined || binding.line > best.line) best = binding;
      }
      return best === undefined ? undefined : { module: best.module, symbol: best.symbol };
    },
  };

  // Import bindings (after the literal: extractImports needs the built model).
  model.importBindings = extractImports(model, statements);

  // Class records from scopes.
  const classScopes = scopes.filter((scope) => scope.kind === 'class');
  model.classes = classScopes.map((scope) => ({
    name: scope.name,
    bases: scope.bases,
    startLine: scope.startLine,
    endLine: scope.endLine,
    methods: scopes
      .filter((s) => s.kind === 'def' && s.parent === scope)
      .map((s) => s.name),
  }));
  const extracted = extractAssignments(model, statements);
  model.assignments = extracted.assignments;
  model.selfAssigns = extracted.selfAssigns;
  model.assignmentTargetChains = extracted.assignmentTargetChains;
  return model;
}
