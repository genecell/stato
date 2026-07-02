"""SKILL.md export — package stato expertise as an Agent Skills directory.

Agent Skills (agentskills.io) is the open standard read by Claude Code,
Codex, Copilot, Cursor, Gemini CLI and others: a directory containing a
SKILL.md with YAML frontmatter (name, description) and markdown
instructions. This export writes the project's stato expertise as one
such skill under .claude/skills/, making it discoverable by every
skills-compatible tool (copy the directory for tools that look elsewhere).
"""
from __future__ import annotations

import re
from pathlib import Path

from stato.core.composer import _discover_modules
from stato.core.module import ModuleType


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "stato-expertise"


def export_skill(project_dir: Path, force: bool = False) -> tuple[Path, str]:
    """Write .claude/skills/stato-<project>/SKILL.md. Returns (path, action)."""
    stato_dir = project_dir / ".stato"
    modules = _discover_modules(stato_dir)
    skills = [m for m in modules if m["module_type"] == ModuleType.SKILL]
    contexts = [m for m in modules if m["module_type"] == ModuleType.CONTEXT]

    project_name = project_dir.name
    description_extra = ""
    if contexts:
        ctx = contexts[0]["namespace"].get(contexts[0]["class_name"])
        project_name = getattr(ctx, "project", project_name)
        description_extra = getattr(ctx, "description", "")

    skill_name = f"stato-{_slug(project_name)}"
    out_dir = project_dir / ".claude" / "skills" / skill_name
    out_path = out_dir / "SKILL.md"

    existed_before = out_path.exists()
    if existed_before and not force:
        return out_path, "exists"

    lines = [
        "---",
        f"name: {skill_name}",
        "description: "
        f"Validated project expertise for {project_name} captured with stato"
        + (f" — {description_extra}" if description_extra else "")
        + ". Use when working in this project to load prior decisions, "
        "parameters, and lessons learned.",
        "---",
        "",
        f"# {project_name} expertise (stato)",
        "",
        "This skill indexes validated agent state stored in `.stato/` "
        "(typed Python modules: context, plan, memory, skills).",
        "",
        "## How to use",
        "",
        "1. Run `stato resume --raw` for a structured recap of project state.",
        "2. Read `.stato/plan.py` for current progress before starting work.",
        "3. Read the relevant `.stato/skills/<name>.py` before performing that task.",
        "4. After meaningful work: update the modules and run `stato validate .stato/`.",
        "",
    ]

    if skills:
        lines.append("## Captured expertise")
        lines.append("")
        for s in skills:
            cls = s["namespace"].get(s["class_name"])
            name = getattr(cls, "name", s["class_name"])
            desc = getattr(cls, "description", "") or (cls.__doc__ or "").strip()
            lines.append(f"- **{name}** (`.stato/{s['rel_path']}`)"
                         + (f" — {desc}" if desc else ""))
        lines.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    return out_path, "overwritten" if existed_before else "created"
