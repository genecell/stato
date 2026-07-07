"""Canonical stato Agent Skill — teaches coding agents how to USE stato.

Single source of truth. `render_skill_md()` stamps the current package version
into the frontmatter `metadata`. The repo file `skills/stato/SKILL.md`, the
`stato skill install` output, and `stato skill show` all derive from here so
nothing can drift (a test asserts the repo file matches).

Distinct from `stato bridge --platform skill`, which exports a *project's*
captured expertise; this skill documents the stato tool itself.
"""
from __future__ import annotations

from pathlib import Path

SKILL_NAME = "stato"

# Per-tool skills directory conventions (verified mid-2026).
# project_dir / <rel> / skills/<name>/SKILL.md ; user scope swaps the root.
_TOOL_DIRS = {
    "claude": ".claude",
    "codex": ".codex",
    "cursor": ".cursor",
    "gemini": ".gemini",
}

# Body (without frontmatter). Frontmatter is added by render_skill_md so the
# version can be stamped from package metadata.
_SKILL_BODY = """\
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
   relevant module (or run the crystallize prompt: `stato crystallize`). Record
   **failures too** ("avoid X because Y"); `stato reflect` surfaces values you
   changed and reverted — dead-ends worth writing down.
4. **Validate** — run `stato validate .stato/` after any change; fix errors
   before continuing. Never leave invalid state on disk.
5. **Persist milestones** — update `.stato/plan.py` step status/output and
   `.stato/memory.py` (phase, reflection, working notes) before stopping or a
   likely compaction.

## Module schemas (all fields except the required ones are optional)
Skill — a reusable technique (`.stato/skills/<name>.py`):
```python
class QCFiltering:
    \"\"\"Quality-control filtering.\"\"\"
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
- **Workspace**: call `stato_workspace(task)` (MCP) or `stato workspace "<task>"`
  each time you start a task to load only the relevant skills (compact
  summaries) instead of reading the whole library; pull a specific lesson with
  `stato_get_skill_section`. Live task query is the primary signal; with no task
  it falls back to the current plan step.
- **MCP**: `stato mcp` exposes state as resources and validate-gated write tools
  (`stato_write_module`, `stato_update_plan_step`, `stato_append_lesson`); an
  agent gets diagnostics back in the tool result and self-corrects in one turn.
- **Hooks**: `stato hooks install [--reminders]` re-injects validated state
  after compaction and nudges you to checkpoint.

## Rules
- Read plan/skills before acting; validate after writing; keep `.stato/` current.
- Prefer editing the smallest module that changed; re-run `stato validate`.
- Capture the WHY (lessons, decisions), not just the WHAT.

## Environment note
Stato installs a console-script into the **active environment's `bin/`** (e.g.
a conda/venv). If `stato` isn't found, activate that environment or use the full
path. Run `stato doctor` to see the resolved binary, version, and project state.
"""


def _description() -> str:
    return (
        "Use stato to persist, validate, and restore an AI agent's cognitive "
        "state (memory, plan, context, skills) as typed Python modules in a "
        ".stato/ directory. Load this when working in a project with a .stato/ "
        "folder: to restore prior context (stato resume), capture what you learn "
        "(crystallize / edit modules), validate before persisting (stato "
        "validate), or share expertise (snapshot/bridge/team). Explains the "
        "operating loop, module schemas, key commands, and MCP/hooks integration."
    )


def render_skill_md(version: str | None = None) -> str:
    """Return the full, spec-valid SKILL.md with version stamped in metadata."""
    if version is None:
        from stato import __version__ as version

    frontmatter = (
        "---\n"
        f"name: {SKILL_NAME}\n"
        f"description: {_description()}\n"
        "license: MIT\n"
        "metadata:\n"
        "  author: Stato\n"
        f"  version: \"{version}\"\n"
        "---\n\n"
    )
    return frontmatter + _SKILL_BODY


def skill_target_dir(tool: str, user: bool, project_dir: Path) -> Path:
    """Resolve the skills/<name>/ directory for a tool (project or user scope)."""
    if tool not in _TOOL_DIRS:
        raise ValueError(f"Unknown tool: {tool}")
    root = Path.home() if user else Path(project_dir)
    return root / _TOOL_DIRS[tool] / "skills" / SKILL_NAME


def all_tools() -> list[str]:
    return list(_TOOL_DIRS.keys())
