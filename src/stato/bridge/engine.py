"""Bridge engine — one content builder, many platform specs.

All markdown-index bridges share the same body (skill table, plan summary,
working rules); a PlatformSpec carries only what differs per platform:
output path, title, frontmatter, and rule phrasing. Adding a platform is
a spec entry, not a new module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from stato.bridge.base import STATO_MARKER, check_existing_bridge
from stato.core.composer import _discover_modules
from stato.core.module import ModuleType
from stato.modules.plan import PlanHelpers

DEFAULT_RULES = [
    "Read .stato/plan.py FIRST to understand current progress",
    "Read relevant skill files BEFORE performing that task",
    'After completing a step, update plan.py: status -> "complete", add output',
    "If you learn something new, add it to the skill's lessons_learned "
    "(or structured lessons) and bump updated_at",
    "Run `stato validate .stato/` after any changes",
    "If validation fails, fix errors before proceeding",
    "After long work sessions or before stopping, update memory.py with current state",
    "If context feels stale (e.g. after compaction), run `stato resume` and read the output",
]


@dataclass
class PlatformSpec:
    key: str                      # platform id used in --platform
    output_path: str              # project-relative output file
    title: str = "# Stato Project"
    rules_header: str = "## Working Rules"
    rules: list[str] = field(default_factory=lambda: list(DEFAULT_RULES))
    frontmatter: str = ""         # e.g. mdc YAML block, written before the marker
    description: str = ""         # one-liner for --help / hooks status


def build_bridge_body(stato_dir: Path, spec: PlatformSpec) -> str:
    """The shared bridge body: intro, skill table, plan summary, rules."""
    modules = _discover_modules(stato_dir)
    skills = [m for m in modules if m["module_type"] == ModuleType.SKILL]
    plans = [m for m in modules if m["module_type"] == ModuleType.PLAN]

    lines = [
        spec.title,
        "",
        "This project uses Stato for structured expertise management.",
        "All agent state lives in .stato/ as validated Python modules.",
        "",
    ]

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
                ", ".join(f"{k}={v}" for k, v in list(params.items())[:3])
                if params else "-"
            )
            lesson_count = _count_lessons(cls)
            lines.append(
                f"| {name} | v{version} | {param_str} | {lesson_count} lessons |"
            )
        lines.append("")
        lines.append("Read .stato/skills/<name>.py for full details when needed.")
        lines.append("")

    for p in plans:
        cls = p["namespace"].get(p["class_name"])
        if cls and hasattr(cls, "steps"):
            done, total = PlanHelpers.progress(cls.steps)
            next_s = PlanHelpers.next_step(cls.steps)
            lines.append("## Current Plan")
            lines.append(f"Objective: {getattr(cls, 'objective', '?')}")
            lines.append(f"Progress: {done}/{total} steps complete")
            if next_s:
                lines.append(
                    f"Current step: Step {next_s['id']} — {next_s['action']} (pending)"
                )
            lines.append(f"Full plan: .stato/{p['rel_path']}")
            lines.append("")

    lines.append(spec.rules_header)
    for i, rule in enumerate(spec.rules, 1):
        lines.append(f"{i}. {rule}")

    return "\n".join(lines) + "\n"


def _count_lessons(cls) -> int:
    structured = getattr(cls, "lessons", None)
    if isinstance(structured, list):
        return len(structured)
    lessons = getattr(cls, "lessons_learned", "")
    if not lessons:
        return 0
    return len([
        ln for ln in lessons.strip().split("\n") if ln.strip().startswith("-")
    ])


def _marker_comment(spec: PlatformSpec) -> str:
    return (
        f"<!-- {STATO_MARKER}. Do not edit manually. "
        f"Regenerate with: stato bridge --platform {spec.key} -->"
    )


def build_bridge_content(stato_dir: Path, spec: PlatformSpec) -> str:
    """Full file content: frontmatter (if any), stato marker, shared body."""
    body = build_bridge_body(stato_dir, spec)
    parts = []
    if spec.frontmatter:
        parts.append(spec.frontmatter.rstrip("\n"))
    parts.append(_marker_comment(spec))
    parts.append("")
    parts.append(body)
    return "\n".join(parts)


def write_bridge(
    project_dir: Path, spec: PlatformSpec, force: bool = False
) -> tuple[Path, str]:
    """Generate and write a bridge file for a platform spec.

    Returns (path, action): created/overwritten/appended/renamed/cancelled.
    """
    stato_dir = project_dir / ".stato"
    output = project_dir / spec.output_path

    action = check_existing_bridge(output, force)

    if action in ("create", "overwrite"):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(build_bridge_content(stato_dir, spec))
        return output, "created" if action == "create" else "overwritten"
    if action == "append":
        existing = output.read_text()
        separator = (
            "\n---\n"
            f"<!-- {STATO_MARKER}. Content below is managed by stato bridge. -->\n"
            f"<!-- Regenerate with: stato bridge --platform {spec.key} -->\n\n"
        )
        output.write_text(existing + "\n" + separator + build_bridge_body(stato_dir, spec))
        return output, "appended"
    if action == "rename":
        alt_path = output.with_name(output.name + ".stato")
        alt_path.parent.mkdir(parents=True, exist_ok=True)
        alt_path.write_text(build_bridge_content(stato_dir, spec))
        return alt_path, "renamed"
    return output, "cancelled"
