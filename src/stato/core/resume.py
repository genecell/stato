"""Resume — structured recap of project state for context restoration."""
from __future__ import annotations

import ast
from pathlib import Path


def load_module_if_exists(path: Path):
    """Read a .py file, exec it, return the first class or None."""
    if not path.exists():
        return None
    source = path.read_text()
    if not source.strip():
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    namespace = {}
    try:
        exec(source, namespace)
    except Exception:
        return None
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            return namespace.get(node.name)
    return None


def generate_resume(stato_dir: Path, brief: bool = False) -> str:
    """Read all modules and produce a structured recap."""
    sections = []

    # 1. Context (project name, description)
    context = load_module_if_exists(stato_dir / "context.py")
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
        sections.append(f"\nCurrent phase: {memory.phase}")
        if hasattr(memory, "known_issues") and memory.known_issues:
            sections.append("Known issues:")
            for k, v in memory.known_issues.items():
                sections.append(f"  {k}: {v}")
        if hasattr(memory, "reflection") and memory.reflection:
            sections.append(
                f"\nReflection:\n{memory.reflection.strip()}"
            )

    # 5. Brief mode: compress to one paragraph
    if brief:
        return generate_brief(context, plan, memory)

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
