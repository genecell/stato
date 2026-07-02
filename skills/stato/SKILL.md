---
name: stato
description: Use stato to persist, validate, and restore an AI agent's cognitive state (memory, plan, context, skills) as typed Python modules in a .stato/ directory. Load this when working in a project with a .stato/ folder: to restore prior context (stato resume), capture what you learn (crystallize / edit modules), validate before persisting (stato validate), or share expertise (snapshot/bridge/team). Explains the operating loop, module schemas, key commands, and MCP/hooks integration.
license: MIT
metadata:
  author: Stato
  version: "0.8.0"
---

# Using stato

Stato stores an AI agent's cognitive state as **validated, typed Python
modules** in a `.stato/` directory, and shares it across sessions, tools, and
teammates. Think "long-term memory for the agent": compaction is working
memory; stato is the durable, on-disk, compiler-checked layer.

## When to use this skill
Use it whenever you work in a project that has (or should have) a `.stato/`
directory: to restore prior context, capture what you learn, or hand work off.

## The operating loop
1. **Restore** — at the start of a session run `stato resume --raw` and read it;
   read `.stato/plan.py` for current progress.
2. **Work** — perform the task, guided by `.stato/skills/<name>.py`.
3. **Capture** — when you learn a parameter, decision, or lesson, update the
   relevant module (or run the crystallize prompt: `stato crystallize`).
4. **Validate** — run `stato validate .stato/` after any change; fix errors
   before continuing. Never leave invalid state on disk.
5. **Persist milestones** — update `.stato/plan.py` step status/output and
   `.stato/memory.py` (phase, reflection, working notes) before stopping or a
   likely compaction.

## Module schemas (all fields except the required ones are optional)
Skill — a reusable technique (`.stato/skills/<name>.py`):
```python
class QCFiltering:
    """Quality-control filtering."""
    name = "qc_filtering"          # required
    version = "1.0.0"
    source = "debugging 2026-06-01"
    confidence = 0.9               # 0-1
    default_params = {"min_genes": 200}
    lessons_learned = "- what worked and why"
    def run(self):                 # required for skills
        ...
```
Plan (`.stato/plan.py`): `name`, `objective`, `steps` (list of
`{"id", "action", "status", "output"}`), `decision_log`.
Memory (`.stato/memory.py`): `phase` (required), `reflection`, `known_issues`,
`updated_at`.
Context (`.stato/context.py`): `project`, `description` (required),
`conventions`, `environment`.

Declare a type explicitly with `__stato_type__ = "skill"` if inference is unsure.

## Key commands
- `stato init` — create `.stato/`.
- `stato resume [--raw|--brief]` — recap current state.
- `stato validate .stato/ [--strict]` — 7-pass validation (nothing invalid persists).
- `stato audit .stato/ [--min N]` — score module quality 0-10 and list gaps.
- `stato status` — modules + plan progress.
- `stato bridge --platform agents|claude|cursor|copilot|gemini` — write an
  instruction file for a tool (AGENTS.md is the cross-tool default).
- `stato snapshot --name X [--template]` / `stato import X.stato` — share/reuse
  whole cognitive-state archives (checksummed).
- `stato merge a.stato b.stato` — combine two archives.
- `stato team assemble` — generate expertise-scoped subagents from `.stato/team.toml`.

## Deeper integration (optional, better UX)
- **MCP**: `stato mcp` exposes state as resources and validate-gated write tools
  (`stato_write_module`, `stato_update_plan_step`, `stato_append_lesson`); an
  agent gets diagnostics back in the tool result and self-corrects in one turn.
- **Hooks**: `stato hooks install [--reminders]` re-injects validated state
  after compaction and nudges you to checkpoint.

## Rules
- Read plan/skills before acting; validate after writing; keep `.stato/` current.
- Prefer editing the smallest module that changed; re-run `stato validate`.
- Capture the WHY (lessons, decisions), not just the WHAT.
