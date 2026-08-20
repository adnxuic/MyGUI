/**
 * Fixed dynamic-Adapter host-code template.
 *
 * The dynamic Cordis package a Scanner Worker mounts is generated from THIS
 * template and nothing else. The template is a pure bridge:
 *
 *   - it resolves the `myguiScanners` registry service (injectable service,
 *     never a private Cordis structure);
 *   - it registers ONE model-facing tool whose `execute` is exactly
 *     `myguiScanners.run(scannerId, request)`;
 *   - it adds no shell, write, or network capability;
 *   - it contains no scanner rules — rules stay in the persistent scanner
 *     implementation under `.dsh/scanners/`.
 *
 * `buildAdapterHostCode(config)` returns the plain-JavaScript function body
 * to pass as `code.host` to `cordis_define`. All injected values are
 * JSON-escaped, so no caller input can escape the template.
 *
 * The single source of truth is `templates/adapter.host.js` (a human-readable
 * copy with `__PLACEHOLDER__` markers); this module reads it at import time,
 * so the two can never drift apart.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { ScannerAdapterConfig } from './contracts.ts';

/** Fixed, closed set of model-facing tool arguments. */
export const TOOL_ARGUMENT_NAMES = ['include', 'exclude', 'changedFiles'] as const;

/**
 * Build the model-facing tool description from scanner metadata.
 * Includes scanner id, version, description, and the read-only declaration.
 */
export function buildToolDescription(input: {
  scannerId: string;
  scannerVersion: string;
  scannerDescription: string;
}): string {
  return [
    `Runs the registered MyGUI scanner "${input.scannerId}" (version ${input.scannerVersion}) against the workspace.`,
    `Scanner: ${input.scannerDescription}`,
    'This tool performs detection only. It does not modify repository files.',
  ].join(' ');
}

/** Path of the human-readable template file (single source of truth). */
const TEMPLATE_PATH = fileURLToPath(new URL('../templates/adapter.host.js', import.meta.url));

/**
 * The template body, read from `templates/adapter.host.js` so the on-disk
 * file and the generated code can never drift apart. The file starts with a
 * comment header explaining the placeholders; comments are harmless inside
 * the generated function body.
 */
const TEMPLATE = readFileSync(TEMPLATE_PATH, 'utf8');

/** Escape a string as a JSON string literal (double-quoted). */
function jsonString(value: string): string {
  return JSON.stringify(value);
}

/** Substitute one placeholder with a JSON-escaped value. */
function substitute(template: string, placeholder: string, value: string): string {
  const marker = `__${placeholder}__`;
  if (!template.includes(marker)) {
    throw new Error(`template placeholder ${marker} not found`);
  }
  return template.split(marker).join(jsonString(value));
}

/**
 * Generate the `code.host` body for the dynamic Scanner Adapter package.
 * Throws on invalid config (empty ids, illegal tool name).
 */
export function buildAdapterHostCode(config: ScannerAdapterConfig): string {
  if (typeof config.scannerId !== 'string' || config.scannerId === '') {
    throw new Error('scannerId must be a non-empty string');
  }
  if (typeof config.toolName !== 'string' || config.toolName === '') {
    throw new Error('toolName must be a non-empty string');
  }
  if (typeof config.toolDescription !== 'string' || config.toolDescription === '') {
    throw new Error('toolDescription must be a non-empty string');
  }
  if (typeof config.workspace !== 'string' || config.workspace === '') {
    throw new Error('workspace must be a non-empty string');
  }

  let code = TEMPLATE;
  code = substitute(code, 'TOOL_NAME', config.toolName);
  code = substitute(code, 'TOOL_DESCRIPTION', config.toolDescription);
  code = substitute(code, 'WORKSPACE', config.workspace);
  code = substitute(code, 'SCANNER_ID', config.scannerId);
  return code;
}
