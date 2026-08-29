---
name: evolve-architecture-rule
description: Review a MyGUI gray architecture boundary and either dismiss it with regression evidence or promote it to a stable invariant and architecture rule.
---

# Evolve Architecture Rule

Read `.agents/architecture/rule-evolution.md`, the owning architecture page,
and current test fixtures. Preserve the existing `CORE-*` invariants and do
not generalize one incident without repository evidence.

Reproduce the candidate, identify its authoritative owner, and classify it as
not a risk, a new invariant, or insufficient evidence. Dismissals require an
explicit rationale plus a negative fixture. Promotions require a stable rule
ID, authoritative architecture source, test enforcement, catalog entry, and
shared check coverage. Update root `AGENTS.md` only for a global CORE
index/summary. Unexplained allowlists are forbidden.
