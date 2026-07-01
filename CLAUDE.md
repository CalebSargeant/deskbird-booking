# CLAUDE.md

Deskbird desk-booking automation: one headless-Chromium/Selenium Python script
(`deskbird_booking.py`) books a desk 7 days ahead via Microsoft SSO with
credentials from 1Password, packaged as a container and run as a Kubernetes
CronJob (firefly cluster, `automation` ns), deployed by Kustomize + SOPS + Flux.

## Commands
See @.claude/QUICK_START.md for the most-run commands (syntax check, docker
build, kustomize, in-cluster inspection, docs). There is **no test suite and no
linter** — validate with `python3 -m py_compile deskbird_booking.py`.

## Architecture
@.claude/ARCHITECTURE_MAP.md

## Gotchas
@.claude/COMMON_MISTAKES.md

## Finding code
- Before locating unfamiliar code, read `./PROJECT_INDEX.json` first (structural
  map: modules, entrypoints, call-graph highlights, hotspots).
- Load `.claude/decisions/` and `.claude/sessions/` ONLY when the task relates to
  them — never by default.
- `AGENTS.md` and `./docs` hold fuller prose if you need background.

## [tooling]
- Prefer targeted line-range reads over whole files; use `PROJECT_INDEX.json` to
  find the location first.
- With grep/find/glob, return matching paths and matched lines only.
- For commands that can flood output (logs, kustomize, page dumps), pipe through
  `head`/`tail`/`grep` or redirect to `.claude/last_output.txt` and read ranges —
  don't paste thousands of lines into context.
- After a successful write/edit, trust it; don't re-read just to "verify".

## [maintenance]
- Bug that took >1h to solve: append it to `.claude/COMMON_MISTAKES.md`.
- Architectural decision: run `/adr`.
- Public behaviour/API/config/setup changed: run `/update-docs`.
- `PROJECT_INDEX.json` stale (new module, big refactor): regenerate only the
  affected `modules` section.
- Keep this file under ~500 tokens; push detail into on-demand `.claude/` files.
