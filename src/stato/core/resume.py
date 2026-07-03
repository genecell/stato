"""Resume — structured recap of project state for context restoration."""
from __future__ import annotations

from pathlib import Path

from stato.core.astload import load_class


def load_module_if_exists(path: Path):
    """Read a .py file and return its first class, built via AST (never executed)."""
    if not path.exists():
        return None
    source = path.read_text()
    if not source.strip():
        return None
    return load_class(source)


def _version_lines(context, stato_dir: Path) -> list[str]:
    """Running-version header + mismatch warning + freshness from mtime."""
    from stato import __version__

    lines = [f"Stato: {__version__}"]

    # Version mismatch: compare running version to any stato version baked in
    # context.environment (their stale-0.5.0 case).
    if context is not None:
        env = getattr(context, "environment", None) or {}
        recorded = env.get("stato") or env.get("stato_version")
        if recorded and str(recorded).lstrip(">=~ ") not in __version__ \
                and __version__ not in str(recorded):
            lines.append(
                f"⚠ version mismatch: state recorded under stato {recorded}, "
                f"running {__version__} — behavior/fields may differ."
            )

    # Freshness from filesystem mtime (survives even without updated_at fields).
    mods = [p for p in stato_dir.rglob("*.py")
            if ".history" not in p.parts and not p.name.startswith("__")]
    if mods:
        import time
        from datetime import datetime, timezone
        newest = max(p.stat().st_mtime for p in mods)
        stamp = datetime.fromtimestamp(newest, tz=timezone.utc).date().isoformat()
        age_days = int((time.time() - newest) / 86400)
        if age_days >= 14:
            lines.append(
                f"⚠ State files last modified {stamp} ({age_days} days ago) — "
                "may be stale; verify against current work before anchoring to it."
            )
        else:
            lines.append(f"State files last modified: {stamp}")
    return lines


def generate_resume(stato_dir: Path, brief: bool = False) -> str:
    """Read all modules and produce a structured recap."""
    sections = []

    # 1. Context (project name, description)
    context = load_module_if_exists(stato_dir / "context.py")

    sections.extend(_version_lines(context, stato_dir))

    if context:
        sections.append(f"Project: {context.project}")
        sections.append(f"Description: {context.description}")
        if hasattr(context, "environment") and context.environment:
            env_str = ", ".join(
                f"{k} {v}" for k, v in context.environment.items()
            )
            sections.append(f"Environment: {env_str}")

    # 2. Plan progress
    plan = load_module_if_exists(stato_dir / "plan.py")
    if plan:
        total = len(plan.steps)
        complete = sum(
            1 for s in plan.steps if s.get("status") == "complete"
        )
        current = next(
            (
                s
                for s in plan.steps
                if s.get("status") in ("running", "pending")
            ),
            None,
        )
        sections.append(f"\nPlan: {plan.name}")
        sections.append(f"Objective: {plan.objective}")
        sections.append(f"Progress: {complete}/{total} steps complete")

        # List completed steps with outputs
        completed_steps = [
            s for s in plan.steps if s.get("status") == "complete"
        ]
        if completed_steps:
            sections.append("Completed:")
            for s in completed_steps:
                output = f" → {s['output']}" if s.get("output") else ""
                sections.append(
                    f"  Step {s['id']}: {s['action']}{output}"
                )

        if current:
            sections.append(
                f"Next: Step {current['id']} — {current['action']}"
            )

        if hasattr(plan, "decision_log") and plan.decision_log:
            sections.append(
                f"\nKey decisions:\n{plan.decision_log.strip()}"
            )

    # 3. Skills summary (names + key params + lesson count)
    skills_dir = stato_dir / "skills"
    if skills_dir.exists():
        skill_files = sorted(skills_dir.glob("*.py"))
        if skill_files:
            skill_entries = []
            for sf in skill_files:
                if sf.name.startswith("__"):
                    continue
                skill = load_module_if_exists(sf)
                if skill:
                    params_str = ""
                    if (
                        hasattr(skill, "default_params")
                        and skill.default_params
                    ):
                        items = list(skill.default_params.items())[:3]
                        params_str = " | " + ", ".join(
                            f"{k}={v}" for k, v in items
                        )
                    lessons_count = ""
                    if (
                        hasattr(skill, "lessons_learned")
                        and skill.lessons_learned
                    ):
                        count = len([
                            ln
                            for ln in skill.lessons_learned.strip().split(
                                "\n"
                            )
                            if ln.strip().startswith("-")
                        ])
                        lessons_count = f" | {count} lessons"
                    skill_entries.append(
                        f"  {skill.name} "
                        f"v{getattr(skill, 'version', '?')}"
                        f"{params_str}{lessons_count}"
                    )
            if skill_entries:
                sections.append("\nAvailable expertise:")
                sections.extend(skill_entries)

    # 4. Memory state
    memory = load_module_if_exists(stato_dir / "memory.py")
    if memory:
        as_of = (
            getattr(memory, "updated_at", None)
            or getattr(memory, "last_updated", None)
        )
        if as_of:
            sections.append(f"\nState as of: {as_of}")
        source_note = getattr(memory, "source", None)
        if source_note:
            sections.append(f"Source: {source_note}")
        sections.append(f"\nCurrent phase: {memory.phase}")
        if hasattr(memory, "known_issues") and memory.known_issues:
            sections.append("Known issues:")
            for k, v in memory.known_issues.items():
                sections.append(f"  {k}: {v}")
        if hasattr(memory, "reflection") and memory.reflection:
            sections.append(
                f"\nReflection:\n{memory.reflection.strip()}"
            )

    # 5. Brief mode: compress to one paragraph (keep version/freshness header)
    if brief:
        header = "\n".join(_version_lines(context, stato_dir))
        return header + "\n" + generate_brief(context, plan, memory)

    return "\n".join(sections)


def generate_brief(context, plan, memory) -> str:
    """One-paragraph summary for quick context restoration."""
    parts = []

    if context:
        parts.append(f"{context.project}: {context.description}.")

    if plan:
        total = len(plan.steps)
        complete = sum(
            1 for s in plan.steps if s.get("status") == "complete"
        )
        current = next(
            (
                s
                for s in plan.steps
                if s.get("status") in ("running", "pending")
            ),
            None,
        )
        parts.append(f"Progress: {complete}/{total} steps complete.")
        if current:
            parts.append(f"Next: {current['action']}.")

    if memory and hasattr(memory, "reflection") and memory.reflection:
        first_sentence = memory.reflection.strip().split(".")[0] + "."
        parts.append(first_sentence)

    return " ".join(parts)
