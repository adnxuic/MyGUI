/**
 * Architecture rule tests: positive and negative fixtures per rule.
 *
 * Every rule must hit its positive fixtures, stay silent on the negative
 * fixture workspace, and produce correct file paths, line numbers, and
 * stable fingerprints.
 */

import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { test } from 'node:test';
import type { ScannerFinding } from '../src/contracts.ts';
import { buildPyFileModel, type PyFileModel } from '../src/lib/py/model.ts';
import { ARCHITECTURE_RULES } from '../src/scanners/architecture/rules/index.ts';

const FIXTURES = resolve(import.meta.dirname, 'fixtures');

function readdirSyncSafe(dir: string): string[] {
  try {
    return readdirSync(dir);
  } catch {
    return [];
  }
}

function loadWorkspace(name: string): PyFileModel[] {
  const root = join(FIXTURES, name);
  const files: PyFileModel[] = [];
  const stack = [root];
  while (stack.length > 0) {
    const dir = stack.pop()!;
    for (const entry of readdirSyncSafe(dir)) {
      const abs = join(dir, entry);
      const rel = abs.slice(root.length + 1).replace(/\\/g, '/');
      if (entry.endsWith('.py')) {
        files.push(buildPyFileModel(rel, readFileSync(abs, 'utf8')));
      } else if (!entry.includes('.')) {
        stack.push(abs);
      }
    }
  }
  files.sort((a, b) => (a.path < b.path ? -1 : 1));
  return files;
}

async function runAllRules(files: PyFileModel[]) {
  const context = { request: {} as never, workspace: FIXTURES, files };
  const findings: ScannerFinding[] = [];
  for (const rule of ARCHITECTURE_RULES) {
    findings.push(...(await rule.run(context)).findings);
  }
  return findings;
}

async function findingsFor(files: PyFileModel[], ruleId: string): Promise<ScannerFinding[]> {
  return (await runAllRules(files)).filter((finding) => finding.ruleId === ruleId);
}

test('ARCH-PRIVATE-CONTAINER-ACCESS: positive fixture hits, owner/subclass accesses do not', async () => {
  const files = loadWorkspace('ws_basic');
  const findings = await findingsFor(files, 'ARCH-PRIVATE-CONTAINER-ACCESS');

  const byLine = new Map(findings.map((finding) => [`${finding.file}:${finding.line}`, finding]));
  // Non-owner class accesses.
  assert.ok(byLine.has('mygui/widgets/fig_control_window/containers.py:31'), 'OtherPanel host._figure_stack access');
  assert.ok(byLine.has('mygui/widgets/fig_control_window/containers.py:34'), 'OtherPanel stack._toolboxes access');
  // Owner and subclass accesses are NOT findings.
  assert.ok(!byLine.has('mygui/widgets/fig_control_window/containers.py:8'), 'owner assignment must not be a finding');
  assert.ok(!byLine.has('mygui/widgets/fig_control_window/containers.py:13'), 'subclass access must not be a finding');
  assert.ok(!byLine.has('mygui/widgets/fig_control_window/containers.py:23'), 'owner assignment must not be a finding');
  assert.ok(!byLine.has('mygui/widgets/fig_control_window/owners_ok.py:13'), 'subclass access must not be a finding');

  for (const finding of findings) {
    assert.equal(finding.file, finding.file.replace(/^\.\//, ''));
    assert.ok(!finding.file.startsWith('/'), 'file must be workspace-relative');
    assert.ok(finding.confidence >= 0 && finding.confidence <= 1);
    assert.equal(finding.severity, 'medium');
  }
});

test('ARCH-UI-ARTIST-MUTATION: positive fixture hits; Qt bindings, axes commands, controllers do not', async () => {
  const files = loadWorkspace('ws_basic');
  const findings = await findingsFor(files, 'ARCH-UI-ARTIST-MUTATION');

  const evidence = findings.map((finding) => finding.evidence);
  assert.ok(evidence.includes('line.set_visible(True)'), 'line.set_visible(True)');
  assert.ok(evidence.includes('line.set_linewidth(2.0)'), 'line.set_linewidth(2.0)');
  assert.ok(
    evidence.some((text) => text.includes('artist.set_visible(False)')),
    'alias-resolved artist.set_visible(False)',
  );
  // Legal paths are not findings.
  assert.ok(!evidence.some((text) => text.includes('_text_binding.set_text')), 'binding set_text is Qt, not artist');
  assert.ok(!evidence.some((text) => text.includes('apply_property')), 'controller call is the sanctioned path');
  assert.ok(findings.every((finding) => finding.severity === 'medium'));
});

test('ARCH-UI-MPL-GLOBAL-STATE-MUTATION: positive fixture hits; reads and config owners do not', async () => {
  const files = loadWorkspace('ws_basic');
  const findings = await findingsFor(files, 'ARCH-UI-MPL-GLOBAL-STATE-MUTATION');

  const evidence = findings.map((finding) => finding.evidence);
  assert.ok(evidence.some((text) => text.includes('mpl.rcParams["text.usetex"] = True')), 'module-alias rcParams assignment');
  assert.ok(evidence.some((text) => text.includes('rcParams["text.usetex"] = True')), 'from-import rcParams assignment');
  assert.ok(
    evidence.some((text) => text.includes('mpl.rcParams.update({"text.usetex": True})')),
    'rcParams.update() call',
  );
  assert.ok(evidence.some((text) => text.includes('mpl.rc("text", usetex=True)')), 'module-alias rc() call');
  assert.ok(evidence.some((text) => text.includes('rc("text", usetex=True)')), 'from-import rc() call');
  assert.ok(findings.every((finding) => finding.severity === 'medium'), 'default severity is warning-equivalent (medium)');
  assert.ok(
    findings.every((finding) => finding.tags.includes('ui-matplotlib-global-state-mutation')),
    'findings carry the ui_matplotlib_global_state_mutation category tag',
  );

  // Legal paths are not findings.
  assert.ok(!evidence.some((text) => text.includes('return mpl.rcParams["text.usetex"]')), 'read is never reported');
  assert.ok(!evidence.some((text) => text.includes('rcParams.get(')), 'rcParams.get(...) is a read');
  assert.ok(
    !evidence.some((text) => text.includes('TexConfigService')),
    'authorized Service class write is not a UI violation',
  );
  assert.ok(
    findings.every((finding) => finding.ruleId === 'ARCH-UI-MPL-GLOBAL-STATE-MUTATION'),
    'the rule stays independent of ARCH-UI-ARTIST-MUTATION',
  );
});

test('ARCH-UI-MPL-GLOBAL-STATE-MUTATION: import bindings are resolved per alias', async () => {
  const files = loadWorkspace('ws_basic');
  const findings = await findingsFor(files, 'ARCH-UI-MPL-GLOBAL-STATE-MUTATION');
  const byLine = new Map(findings.map((finding) => [`${finding.file}:${finding.line}`, finding]));

  // mpl_global.py lines (1-based) of each sink.
  assert.ok(byLine.has('mygui/widgets/ui/mpl_global.py:9'), 'mpl.rcParams assignment');
  assert.ok(byLine.has('mygui/widgets/ui/mpl_global.py:12'), 'rcParams assignment via from-import');
  assert.ok(byLine.has('mygui/widgets/ui/mpl_global.py:15'), 'mpl.rcParams.update');
  assert.ok(byLine.has('mygui/widgets/ui/mpl_global.py:18'), 'mpl.rc(...)');
  assert.ok(byLine.has('mygui/widgets/ui/mpl_global.py:21'), 'rc(...) via from-import');

  // The assignment finding reports the concrete key.
  const assignment = byLine.get('mygui/widgets/ui/mpl_global.py:9')!;
  assert.ok(assignment.reason.includes('text.usetex'), 'assignment reason carries the rcParams key');
  assert.equal(assignment.confidence, 0.9);

  // Reads on lines 24/27 are absent.
  assert.ok(!byLine.has('mygui/widgets/ui/mpl_global.py:24'), 'read must not be reported');
  assert.ok(!byLine.has('mygui/widgets/ui/mpl_global.py:27'), 'rcParams.get read must not be reported');
});

test('ARCH-SECOND-COMPONENT-STATE: positive fixture hits; canvas writes do not', async () => {
  const files = loadWorkspace('ws_basic');
  const findings = await findingsFor(files, 'ARCH-SECOND-COMPONENT-STATE');

  const byLine = new Map(findings.map((finding) => [`${finding.file}:${finding.line}`, finding]));
  assert.ok(byLine.has('mygui/widgets/ui/panel.py:32'), 'self.current_component_id = None');
  assert.ok(byLine.has('mygui/widgets/ui/panel.py:36'), 'ComponentState(...) construction');
  assert.ok(findings.every((finding) => finding.severity === 'high'));
});

test('ARCH-CONTROLLER-BYPASS: positive fixture hits; reads and domain writes do not', async () => {
  const files = loadWorkspace('ws_basic');
  const findings = await findingsFor(files, 'ARCH-CONTROLLER-BYPASS');

  const evidence = findings.map((finding) => finding.evidence);
  assert.ok(evidence.some((text) => text.includes('controller.state.properties["visible"] = True')), 'state dict write');
  assert.ok(evidence.some((text) => text.includes('controller.state = None')), 'whole-state replacement');
  assert.ok(evidence.some((text) => text.includes('state.data.update({"subplot": {}})')), 'state dict update()');
  assert.ok(evidence.some((text) => text.includes('state.properties.setdefault("visible", True)')), 'state dict setdefault()');
  // Reads are never reported.
  assert.ok(!evidence.some((text) => text.includes('state.data.get("subplot")')), 'state.data.get(...) is a read');
  assert.ok(!evidence.some((text) => text.includes('state.properties.get("visible")')), 'state.properties.get(...) is a read');
  assert.ok(findings.every((finding) => finding.severity === 'high'));
});

test('ARCH-QSETTINGS-BACKEND-BYPASS: positive fixture hits; storage adapter and annotations do not', async () => {
  const files = loadWorkspace('ws_basic');
  const findings = await findingsFor(files, 'ARCH-QSETTINGS-BACKEND-BYPASS');
  const evidence = findings.map((finding) => finding.evidence);
  const byLine = new Map(findings.map((finding) => [`${finding.file}:${finding.line}`, finding]));

  assert.ok(byLine.has('mygui/widgets/ui/qsettings_bypass.py:7'), 'QSettings() construction');
  assert.ok(byLine.has('mygui/widgets/ui/qsettings_bypass.py:8'), 'beginGroup mutation');
  assert.ok(byLine.has('mygui/widgets/ui/qsettings_bypass.py:9'), 'setValue mutation');
  assert.ok(byLine.has('mygui/widgets/ui/qsettings_bypass.py:10'), 'endGroup mutation');
  assert.ok(byLine.has('mygui/figuremodify/qsettings_bypass.py:6'), 'non-widget QSettings construction');
  assert.ok(
    evidence.some((text) => text.includes('QS()') || text.includes('return QS()')),
    'QS = QSettings alias construction',
  );
  assert.ok(
    evidence.some((text) => text.includes('prefs.setValue')),
    'prefs = settings alias setValue',
  );
  assert.ok(!byLine.has('mygui/widgets/ui/qsettings_bypass.py:12'), 'QSettings type annotation is not a construction');
  assert.ok(evidence.every((text) => !text.includes('QSettings | None')), 'annotations are not findings');
  assert.ok(findings.every((finding) => finding.severity === 'high'));
  assert.ok(findings.every((finding) => finding.tags.includes('qsettings-backend-bypass')));
});

test('ARCH-UI-THEME-BYPASS: positive fixture hits; widget-local setFont does not', async () => {
  const files = loadWorkspace('ws_basic');
  const findings = await findingsFor(files, 'ARCH-UI-THEME-BYPASS');
  const evidence = findings.map((finding) => finding.evidence);
  const byLine = new Map(findings.map((finding) => [`${finding.file}:${finding.line}`, finding]));

  assert.ok(byLine.has('mygui/widgets/ui/theme_bypass.py:7'), 'app.setFont');
  assert.ok(byLine.has('mygui/widgets/ui/theme_bypass.py:8'), 'app.setPalette');
  assert.ok(byLine.has('mygui/widgets/ui/theme_bypass.py:9'), 'app.setStyleSheet');
  assert.ok(byLine.has('mygui/widgets/ui/theme_bypass.py:10'), 'QApplication.setFont');
  assert.ok(
    evidence.some((text) => text.includes('QApplication.instance().setFont')),
    'QApplication.instance().setFont is visible after call-chain continuation',
  );
  assert.ok(!byLine.has('mygui/widgets/ui/theme_bypass.py:18'), 'title.setFont is widget-local');
  assert.ok(!evidence.some((text) => text.includes('title.setFont')));
  assert.ok(findings.every((finding) => finding.severity === 'high'));
  assert.ok(findings.every((finding) => finding.tags.includes('ui-theme-bypass')));
});

test('QSS color completeness is not a lexical architecture rule', async () => {
  assert.ok(
    !ARCHITECTURE_RULES.some((rule) => /qss|color-complete|hex/i.test(rule.id)),
    'bundled QSS hex completeness stays a Python contract test',
  );
});

test('negative workspace produces zero findings', async () => {
  const files = loadWorkspace('ws_negative');
  const findings = await runAllRules(files);
  assert.deepEqual(findings, [], `unexpected findings: ${JSON.stringify(findings.map((f) => [f.ruleId, f.file, f.line]))}`);
});

test('line numbers and workspace-relative paths are exact', async () => {
  const files = loadWorkspace('ws_basic');
  const findings = await runAllRules(files);
  const target = findings.find(
    (finding) =>
      finding.ruleId === 'ARCH-UI-ARTIST-MUTATION' &&
      finding.file === 'mygui/widgets/ui/panel.py' &&
      finding.evidence.includes('set_visible'),
  );
  assert.ok(target, 'artist mutation finding exists');
  assert.equal(target.line, 13);
  assert.equal(target.file, 'mygui/widgets/ui/panel.py');
  assert.ok(target.evidence.includes('line.set_visible(True)'));
});

test('fingerprints are stable across runs and whitespace edits', async () => {
  const first = await runAllRules(loadWorkspace('ws_basic'));
  const second = await runAllRules(loadWorkspace('ws_basic'));
  assert.deepEqual(
    first.map((finding) => finding.fingerprint).sort(),
    second.map((finding) => finding.fingerprint).sort(),
    'fingerprints must be deterministic across runs',
  );

  // A finding whose evidence only changes whitespace keeps its fingerprint.
  const finding = first.find((f) => f.ruleId === 'ARCH-UI-ARTIST-MUTATION' && f.line === 13)!;
  const reFingerprint = finding.fingerprint;
  assert.equal(reFingerprint.length, 40, 'sha1 hex');
});
