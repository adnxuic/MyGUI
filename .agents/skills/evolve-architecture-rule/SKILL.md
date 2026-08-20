---
name: evolve-architecture-rule
description: Review a MyGUI gray architecture boundary and either dismiss it with regression evidence or promote it to a stable invariant and Scanner rule.
---

# Evolve Architecture Rule

Read `.agents/architecture/rule-evolution.md`, the owning architecture page,
and current Scanner fixtures. Preserve the existing `CORE-*` invariants and do
not generalize one incident without repository evidence.

Reproduce the candidate, identify its authoritative owner, and classify it as
not a risk, a new invariant, or insufficient evidence. Dismissals require an
explicit rationale plus a negative fixture. Promotions require a stable rule
ID, architecture update, global `AGENTS.md` update only when applicable,
Scanner implementation, positive/negative fixtures, catalog entry, and shared
check coverage. Unexplained allowlists are forbidden.
