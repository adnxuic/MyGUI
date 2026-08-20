# Architecture Rule Evolution

Scanner rules evolve from repository evidence, not from isolated stylistic
preferences.

1. Record a candidate in `grayBoundaries[]` with a stable fingerprint,
   evidence, scope, why it is not yet a violation, and the proposed risk.
2. Reproduce it and inspect the authoritative owner and existing tests.
3. Classify it as `not_a_risk`, `new_invariant`, or `insufficient_evidence`.
4. For `not_a_risk`, record the rationale in the scanner fixture/test and keep
   an explicit negative example; do not add an unexplained allowlist.
5. For `new_invariant`, allocate a stable rule ID, update the relevant
   architecture page, update `AGENTS.md` only if repository-global, implement
   the Scanner rule, and add positive and negative fixtures.
6. Update `rule-catalog.yaml`, task routing, shared checks, and documentation
   ownership in the same change.
7. Run `verify_agent_core` and `verify_architecture`; an architecture-audit
   task with unresolved `insufficient_evidence` cannot report completed.

Rule IDs are immutable once published. Severity changes and scope expansions
require test evidence. A Scanner must report parse/read failures as errors and
`unknown`, never as clean coverage.
