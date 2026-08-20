/**
 * Standalone CLI for the architecture scanner — used for local verification
 * without a DSH host:
 *
 *   node dist/cli/scan.js <workspace> [--json] [--max N]
 */

import { resolve } from 'node:path';
import { createArchitectureScanner } from '../scanners/architecture/scanner.ts';

function printUsage(): void {
  process.stderr.write(
    'usage: node dist/cli/scan.js <workspace> [--json] [--max <n>] [--include <glob>] [--exclude <glob>]\n',
  );
}

async function main(argv: string[]): Promise<number> {
  const positional: string[] = [];
  let json = false;
  let maxFindings = 8;
  const include: string[] = [];
  const exclude: string[] = [];
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]!;
    if (arg === '--json') json = true;
    else if (arg === '--max') {
      i += 1;
      maxFindings = Number.parseInt(argv[i] ?? '8', 10);
    } else if (arg === '--include') {
      i += 1;
      include.push(argv[i] ?? '');
    } else if (arg === '--exclude') {
      i += 1;
      exclude.push(argv[i] ?? '');
    } else if (arg === '--help' || arg === '-h') {
      printUsage();
      return 0;
    } else {
      positional.push(arg);
    }
  }
  if (positional.length !== 1) {
    printUsage();
    return 2;
  }

  const workspace = resolve(positional[0]!);
  const scanner = createArchitectureScanner();
  const result = await scanner.run({ workspace, include, exclude });

  if (json) {
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return 0;
  }

  const { summary } = result;
  process.stdout.write(`scanner      : ${result.scannerId} v${result.scannerVersion}\n`);
  process.stdout.write(`workspace    : ${result.workspace}\n`);
  process.stdout.write(`revision     : ${result.revision ?? '(unknown)'}\n`);
  process.stdout.write(`files scanned: ${result.filesScanned}\n`);
  process.stdout.write(`duration     : ${result.durationMs} ms\n`);
  process.stdout.write(`findings     : ${summary.total} (${Object.entries(summary.bySeverity)
    .map(([severity, count]) => `${severity}: ${count}`)
    .join(', ')})\n`);
  if (result.diagnostics.length > 0) {
    process.stdout.write('diagnostics  :\n');
    for (const diagnostic of result.diagnostics) {
      process.stdout.write(`  [${diagnostic.level}] ${diagnostic.file ?? ''} ${diagnostic.message}\n`);
    }
  }
  for (const finding of result.findings.slice(0, maxFindings)) {
    process.stdout.write(
      `\n[${finding.severity}/${finding.confidence}] ${finding.ruleId} ${finding.file}:${finding.line ?? '-'}\n` +
        `  ${finding.title}\n  ${finding.evidence}\n`,
    );
  }
  if (result.findings.length > maxFindings) {
    process.stdout.write(`\n... ${result.findings.length - maxFindings} more findings (use --max <n> or --json)\n`);
  }
  return 0;
}

main(process.argv.slice(2)).then(
  (code) => {
    process.exitCode = code;
  },
  (error) => {
    process.stderr.write(`scan failed: ${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
    process.exitCode = 1;
  },
);
