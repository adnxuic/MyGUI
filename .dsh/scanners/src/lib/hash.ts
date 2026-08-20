/**
 * Stable fingerprinting for findings. Same code + same rule ⇒ same
 * fingerprint, across runs and machines.
 */

import { createHash } from 'node:crypto';

/** Collapse whitespace runs so evidence edits do not change the fingerprint. */
function normalizeText(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

/** Build the stable fingerprint for one finding. */
export function fingerprintFor(ruleId: string, file: string, line: number | undefined, evidence: string): string {
  const payload = [ruleId, file, line ?? 0, normalizeText(evidence)].join('|');
  return createHash('sha1').update(payload).digest('hex');
}
