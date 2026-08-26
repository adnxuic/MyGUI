/** Standalone deterministic CLI for registered production scanner factories. */

import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import type { ScannerDefinition } from '../contracts.ts';
import { validateScannerResult } from '../validation.ts';
import { createArchitectureScanner } from '../scanners/architecture/scanner.ts';
import { createQtLifecycleScanner } from '../scanners/qt-lifecycle/scanner.ts';

const FACTORIES: Record<string, () => ScannerDefinition> = {
  'mygui.architecture': createArchitectureScanner,
  'mygui.qt-lifecycle': createQtLifecycleScanner,
};

function usage(): void {
  process.stderr.write(
    'usage: node dist/cli/scan.js <workspace> [--scanner <id>] [--json] [--json-out <path>] [--max <n>] [--include <glob>] [--exclude <glob>] [--fail-on-gray]\n',
  );
}

async function main(argv: string[]): Promise<number> {
  const positional: string[] = [];
  let scannerId = 'mygui.architecture';
  let json = false;
  let jsonOut: string | undefined;
  let maxFindings = 8;
  let failOnGray = false;
  const include: string[] = [];
  const exclude: string[] = [];
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]!;
    if (arg === '--json') json = true;
    else if (arg === '--scanner') scannerId = argv[++i] ?? '';
    else if (arg === '--json-out') jsonOut = argv[++i];
    else if (arg === '--max') maxFindings = Number.parseInt(argv[++i] ?? '8', 10);
    else if (arg === '--include') include.push(argv[++i] ?? '');
    else if (arg === '--exclude') exclude.push(argv[++i] ?? '');
    else if (arg === '--fail-on-gray') failOnGray = true;
    else if (arg === '--help' || arg === '-h') { usage(); return 0; }
    else positional.push(arg);
  }
  if (positional.length !== 1 || FACTORIES[scannerId] === undefined) {
    usage();
    if (FACTORIES[scannerId] === undefined) process.stderr.write(`unknown scanner: ${scannerId}\n`);
    return 2;
  }
  const scanner = FACTORIES[scannerId]!();
  const result = await scanner.run({ workspace: resolve(positional[0]!), include, exclude });
  validateScannerResult(result, scannerId);
  const serialized = `${JSON.stringify(result, null, 2)}\n`;
  if (jsonOut) {
    const outputPath = resolve(jsonOut);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, serialized, 'utf8');
  }
  if (json) process.stdout.write(serialized);
  else {
    process.stdout.write(`scanner      : ${result.scanner.id} v${result.scanner.version}\n`);
    process.stdout.write(`status       : ${result.status}\nverdict      : ${result.verdict}\n`);
    process.stdout.write(`workspace    : ${result.scope.workspace}\nrevision     : ${result.scope.revision ?? '(unknown)'}\n`);
    process.stdout.write(`files visited: ${result.coverage.filesVisited.length}\nfiles skipped: ${result.coverage.filesSkipped.length}\n`);
    process.stdout.write(`duration     : ${result.durationMs} ms\n`);
    process.stdout.write(`findings     : ${result.summary.findings}\ngray boundary: ${result.summary.grayBoundaries}\nerrors       : ${result.summary.errors}\n`);
    for (const finding of result.findings.slice(0, maxFindings)) {
      process.stdout.write(`\n[${finding.severity}/${finding.confidence}] ${finding.ruleId} ${finding.file}:${finding.line ?? '-'}\n  ${finding.title}\n  ${finding.evidence}\n`);
    }
  }
  if (result.status === 'failed' || result.status === 'partial') return 1;
  if (result.verdict === 'violation' || result.verdict === 'unknown') return 1;
  if (failOnGray && result.verdict === 'gray_boundary') return 1;
  return 0;
}

main(process.argv.slice(2)).then(
  (code) => { process.exitCode = code; },
  (error) => {
    process.stderr.write(`scan failed: ${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
    process.exitCode = 1;
  },
);
