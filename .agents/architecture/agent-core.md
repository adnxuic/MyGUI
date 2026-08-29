# Agent Core Governance

Use this page for changes to repository agent instructions, task routing,
Skills, rule catalogs, result contracts, shared checks, or Codex adapters.
It governs Agent Engineering only and does not authorize MyGUI runtime or
project-schema changes.

## Authority and loading

Root `AGENTS.md` is the compact global entry and CORE rule index. The exact
source named by `.agents/rule-catalog.yaml` holds each rule's detailed
normative text. `.agents/task-map.yaml` is the only task-routing source;
matching routes are combined, and their Skills and architecture pages are read
before implementation. Skills define task procedure without redefining the
rules. User documentation cannot override Agent Core.

## Stable contracts

Rule IDs remain stable and catalog entries retain one source plus non-empty
enforcement. TaskResult v1 and ScannerResult v2 change only through an explicit
contract migration. Codex owns requested repository edits and verification.
Generated evidence stays under ignored `build/agent-results/`.

The root entry deliberately retains the explicit Matplotlib process-global
mutation prohibition. Do not move or weaken that clause without updating its
contract tests in the same change.

## Change discipline

Agent Core changes preserve the complete CORE rule set, source anchors,
enforcement targets, required routes, and adapter separation. Update root
`AGENTS.md` only for bootstrap flow or global CORE rule index changes. Put
implementation maps in architecture pages and task procedure in Skills. A
failed, unknown, or not-run required gate blocks completion.
