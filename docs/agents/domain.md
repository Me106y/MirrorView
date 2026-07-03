# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Configured layout

This repo is configured as **single-context**:

- `CONTEXT.md` at the repo root
- `docs/adr/` at the repo root

## Before exploring, read these

- **`CONTEXT.md`** at the repo root.
- **`docs/adr/`** -- read ADRs that touch the area you're about to work in.

If either is missing, proceed silently. Don't flag their absence and don't suggest creating them upfront. The `/domain-modeling` skill can create them lazily when terms or decisions are actually resolved.

## File structure

Single-context repo (this repo):

```
/
|-- CONTEXT.md
|-- docs/adr/
|   |-- 0001-example-decision.md
|   `-- 0002-example-decision.md
`-- src/
```

## Use the glossary's vocabulary

When your output names a domain concept (issue title, refactor proposal, hypothesis, test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal -- either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> Contradicts ADR-0007 -- but worth reopening because...
