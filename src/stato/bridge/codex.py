"""Codex bridge — generates AGENTS.md."""
from __future__ import annotations

from pathlib import Path

from stato.bridge.base import BridgeBase
from stato.core.composer import _discover_modules
from stato.core.module import ModuleType
from stato.modules.plan import PlanHelpers


class CodexBridge(BridgeBase):
    def output_filename(self) -> str:
        return "AGENTS.md"

    def generate(self) -> str:
        modules = _discover_modules(self.stato_dir)
        skills = [m for m in modules if m["module_type"] == ModuleType.SKILL]
        plans = [m for m in modules if m["module_type"] == ModuleType.PLAN]

        lines = [
            "# Stato Project",
            "",
            "This project uses Stato for structured expertise management.",
            "All agent state lives in .stato/ as validated Python modules.",
            "",
        ]

        # Skill table
        if skills:
            lines.append("## Available Skills")
            lines.append("| Skill | Version | Key Parameters | Lessons |")
            lines.append("|---|---|---|---|")
            for s in skills:
                cls = s["namespace"].get(s["class_name"])
                name = getattr(cls, "name", "?")
                version = getattr(cls, "version", "-")
                params = getattr(cls, "default_params", {})
                param_str = (
                    ", ".join(
                        f"{k}={v}" for k, v in list(params.items())[:3]
                    )
                    if params
                    else "-"
                )
                lessons = getattr(cls, "lessons_learned", "")
                lesson_count = (
                    len([
                        ln
                        for ln in lessons.strip().split("\n")
                        if ln.strip().startswith("-")
                    ])
                    if lessons
                    else 0
                )
                lines.append(
                    f"| {name} | v{version} | {param_str} | "
                    f"{lesson_count} lessons |"
                )
            lines.append("")
            lines.append(
                "Read .stato/skills/<name>.py for full details when needed."
            )
            lines.append("")

        # Plan summary
        for p in plans:
            cls = p["namespace"].get(p["class_name"])
            if cls and hasattr(cls, "steps"):
                done, total = PlanHelpers.progress(cls.steps)
                next_s = PlanHelpers.next_step(cls.steps)
                lines.append("## Current Plan")
                lines.append(
                    f"Objective: {getattr(cls, 'objective', '?')}"
                )
                lines.append(f"Progress: {done}/{total} steps complete")
                if next_s:
                    lines.append(
                        f"Current step: Step {next_s['id']} "
                        f"— {next_s['action']} (pending)"
                    )
                lines.append(f"Full plan: .stato/{p['rel_path']}")
                lines.append("")

        # Working rules
        lines.extend([
            "## Working Rules",
            "1. Read .stato/plan.py FIRST to understand current progress",
            "2. Read relevant skill files BEFORE performing that task",
            '3. After completing a step, update plan.py: '
            'status -> "complete", add output',
            "4. If you learn something new, add to the skill's lessons_learned",
            "5. Run `stato validate .stato/` after any changes",
            "6. If validation fails, fix errors before proceeding",
            "7. After long work sessions or before stopping, update memory.py with current state",
            "8. If context feels stale (e.g. after /compact), run `stato resume` and read the output",
        ])

        return "\n".join(lines) + "\n"


def generate_bridge(project_dir: Path, force: bool = False) -> tuple[Path, str]:
    """Generate and write the Codex bridge."""
    bridge = CodexBridge(project_dir)
    return bridge.write(force=force)
