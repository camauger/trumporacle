# Contributing to TRUMPORACLE

This project adopts the **Operational Principles** in [`.cursor/rules/operational-principles.mdc`](.cursor/rules/operational-principles.mdc). They apply to humans and to AI-assisted edits (Cursor rule: `alwaysApply: true`).

## Summary

| Principle | In practice here |
|-----------|------------------|
| **1 — Clarify** | If the spec (`trumporacle.mdc`) or stack (`stack.md`) is ambiguous for your change, ask before coding; state assumptions if you must proceed. |
| **2 — Minimum** | Smallest diff that meets the spec; no new dependency unless justified against `stack.md`. |
| **3 — Scope** | No drive-by refactors or unrelated fixes; flag adjacent bugs, do not fix unless agreed. |
| **4 — Verify** | Define **testable** success criteria before coding; after coding run checks below (or say explicitly what was not run). |
| **5 — Report** | For non-trivial work, end with **Done / Decided / Not done / Not verified / Spotted**. |

## Verification commands (before merge)

```bash
just lint
just test
just typecheck   # if you touched prediction/, evaluation/, or features/
```

Optional: DB integration tests require `DATABASE_URL` and applied migrations (see `README.md`).

## Success criteria (examples)

- *Done = new migration applies on Timescale+vector image, `pytest` green, no new ruff violations.*
- *Done = feature at `H` uses only rows with `published_at <= H`; hypothesis/property or unit test added.*

If you cannot run commands locally, say so in the PR description under **Not verified**.

## Frozen documents

Changes to [`trumporacle.mdc`](trumporacle.mdc) or [`stack.md`](stack.md) need explicit intent (versioning, maintainer decision), not silent edits.

## Further context

- [`AGENTS.md`](AGENTS.md) — architecture and AI-oriented guidelines.
- [`claude.md`](claude.md) — short Claude Code entry point.
