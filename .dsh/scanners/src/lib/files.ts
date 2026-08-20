/**
 * Workspace file discovery for scanners: deterministic, read-only walking of
 * Python sources with include/exclude glob support and cancellation.
 */

import { readdir, stat } from "node:fs/promises";
import { join, relative, sep } from 'node:path';

export interface FileCollectionOptions {
  workspace: string;
  include?: string[];
  exclude?: string[];
  changedFiles?: string[];
  signal?: AbortSignal;
}

export async function workspaceDirectoryExists(workspace: string): Promise<boolean> {
  try {
    return (await stat(workspace)).isDirectory();
  } catch {
    return false;
  }
}

function assertNotAborted(signal?: AbortSignal): boolean {
  // A pre-aborted signal yields an empty (or partial) result rather than
  // throwing: cancellation is a normal outcome, not an error.
  return !signal?.aborted;
}

/** Convert a glob-ish pattern to a RegExp (supports `**`, `*`, `?`). */
export function globToRegExp(pattern: string): RegExp {
  const normalized = pattern.replace(/\\/g, '/');
  let source = '^';
  let i = 0;
  while (i < normalized.length) {
    const ch = normalized[i]!;
    if (ch === '*') {
      if (normalized[i + 1] === '*') {
        // `**` matches any number of path segments (including none).
        if (normalized[i + 2] === '/') {
          source += '(?:.*/)?';
          i += 3;
          continue;
        }
        source += '.*';
        i += 2;
        continue;
      }
      source += '[^/]*';
      i += 1;
      continue;
    }
    if (ch === '?') {
      source += '[^/]';
      i += 1;
      continue;
    }
    source += ch.replace(/[.+^${}()|[\]\\]/g, '\\$&');
    i += 1;
  }
  source += '$';
  return new RegExp(source);
}

/** Compile a pattern list; a pattern without `/` also matches any basename. */
function compilePatterns(patterns: string[]): RegExp[] {
  return patterns.map((pattern) => {
    const re = globToRegExp(pattern);
    if (pattern.includes('/')) return re;
    // Bare name: match the basename at any depth.
    return new RegExp(`(?:^|/)${pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '[^/]*').replace(/\?/g, '[^/]')}$`);
  });
}

function matchesAny(relPath: string, patterns: RegExp[]): boolean {
  for (const re of patterns) {
    if (re.test(relPath)) return true;
  }
  return false;
}

/** Directories never walked (VCS, dependency, build, and cache output). */
const SKIP_DIRS = new Set([
  '.git', '.hg', '.svn',
  'node_modules', 'bower_components',
  '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache', 'htmlcov',
  'dist', 'build', 'out', 'site', '.dsh-home',
]);

/**
 * Collect workspace-relative file paths of `.py` files under `workspace`,
 * deterministically sorted. `changedFiles` (when provided) restricts the
 * result to that set. `include`/`exclude` are additional glob filters.
 */
export async function collectPythonFiles(options: FileCollectionOptions): Promise<string[]> {
  const { workspace } = options;
  const include = compilePatterns(options.include ?? []);
  const exclude = compilePatterns(options.exclude ?? []);

  const all: string[] = [];
  if (!assertNotAborted(options.signal)) return all;
  const stack = [workspace];

  while (stack.length > 0) {
    if (!assertNotAborted(options.signal)) break;
    const dir = stack.pop()!;
    let entries;
    try {
      entries = await readdir(dir, { withFileTypes: true });
    } catch {
      continue; // Unreadable directories are skipped silently.
    }
    entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    for (const entry of entries) {
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name)) stack.push(join(dir, entry.name));
        continue;
      }
      if (!entry.isFile()) continue;
      const abs = join(dir, entry.name);
      const rel = relative(workspace, abs).split(sep).join('/');
      if (!rel.endsWith('.py')) continue;
      if (matchesAny(rel, exclude)) continue;
      if (include.length > 0 && !matchesAny(rel, include)) continue;
      all.push(rel);
    }
  }

  let selected = all;
  if (options.changedFiles !== undefined && options.changedFiles.length > 0) {
    const wanted = new Set(options.changedFiles.map((f) => f.replace(/\\/g, '/')));
    selected = all.filter((rel) => wanted.has(rel));
  }
  selected.sort();
  return selected;
}

/** True when a workspace-relative path belongs to test code. */
export function isTestPath(relPath: string): boolean {
  const normalized = relPath.replace(/\\/g, '/');
  if (normalized.startsWith('tests/')) return true;
  if (normalized.includes('/tests/')) return true;
  const basename = normalized.split('/').pop() ?? '';
  return basename.startsWith('test_') || basename.endsWith('_test.py');
}

/** Read one file's text; returns undefined when the file cannot be read. */
export async function readFileText(absPath: string): Promise<string | undefined> {
  try {
    const { readFile } = await import('node:fs/promises');
    const buffer = await readFile(absPath);
    // Replace invalid UTF-8 sequences rather than failing the whole scan.
    return new TextDecoder('utf-8', { fatal: false }).decode(buffer);
  } catch {
    return undefined;
  }
}

/** Resolve a workspace-relative path against the workspace root. */
export function resolveWorkspacePath(workspace: string, relPath: string): string {
  return join(workspace, ...relPath.split('/'));
}
