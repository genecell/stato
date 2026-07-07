"""Workspace — assemble the task-relevant working set of skills.

Inspired by the "global workspace" in LLMs (a small, capacity-limited,
task-selected set of representations broadcast to many computations): stato
assembles a small working set of skills for the agent's *current task*, projects
them to summaries, and leaves everything else as a one-line index to pull on
demand.

Selection signal ladder (degrades gracefully):
  1. task query given (warm)  -> rank skills against the task (core.search)
  2. no task (cold)           -> current plan step's skills_used, else the
                                 step action + plan objective as an implicit query
  3. neither                  -> index-only

Pins (skills with `always_load = True`, or names in `context.pinned_skills`)
always enter the working set — the paper's "directed modulation", declared in
the validated modules rather than a sidecar. Stateless: recomputed each call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkspaceItem:
    name: str
    rel_path: str
    reason: str          # "task match" | "plan step" | "pinned"
    summary: str         # rendered v0.9 summary (token-efficient projection)


@dataclass
class WorkspaceView:
    signal: str          # "task" | "plan" | "none"
    task: str | None
    active: list[WorkspaceItem] = field(default_factory=list)
    index: list[dict] = field(default_factory=list)   # {name, rel_path, description}
    budget: int | None = None

    def to_dict(self) -> dict:
        return {
            "signal": self.signal,
            "task": self.task,
            "active": [vars(i) for i in self.active],
            "index": self.index,
            "budget": self.budget,
        }

    def render(self) -> str:
        lines = []
        if self.signal == "task":
            lines.append(f"# Workspace for: {self.task}")
        elif self.signal == "plan":
            lines.append("# Workspace (from current plan step — state your task "
                         "with stato_workspace(task) for a live set)")
        else:
            lines.append("# Workspace (no task/plan signal — index only)")

        if self.active:
            lines.append("\n## Active skills")
            for item in self.active:
                lines.append(f"\n<!-- {item.reason} -->")
                lines.append(item.summary)
        if self.index:
            lines.append("\n## Available (pull on demand)")
            for entry in self.index:
                desc = f" — {entry['description']}" if entry["description"] else ""
                lines.append(f"- {entry['name']} (`{entry['rel_path']}`){desc}")
            lines.append("\nPull a lesson via stato_get_skill_section(skill, id), "
                         "or narrow the set with stato_workspace(task).")
        return "\n".join(lines)


def _skill_modules(stato_dir: Path) -> list[dict]:
    from stato.core.composer import _discover_modules
    from stato.core.module import ModuleType

    return [m for m in _discover_modules(stato_dir)
            if m["module_type"] == ModuleType.SKILL]


def _skill_cls(mod: dict):
    return mod["namespace"].get(mod["class_name"]) if mod.get("namespace") else None


def _skill_name(mod: dict) -> str:
    cls = _skill_cls(mod)
    return getattr(cls, "name", mod["class_name"]) if cls else mod["class_name"]


def _skill_search_item(mod: dict) -> dict:
    cls = _skill_cls(mod)
    desc = (getattr(cls, "description", "") or (cls.__doc__ or "")) if cls else ""
    lessons = getattr(cls, "lessons_learned", "") if cls else ""
    structured = getattr(cls, "lessons", None) if cls else None
    if isinstance(structured, list):
        lessons += " " + " ".join(
            f"{e.get('condition','')} {e.get('recommendation','')}"
            for e in structured if isinstance(e, dict))
    return {
        "_mod": mod,
        "name": _skill_name(mod),
        "description": desc,
        "tags": list(getattr(cls, "tags", []) or []) if cls else [],
        "lessons": lessons,
    }


def _pinned_names(stato_dir: Path, skills: list[dict]) -> set[str]:
    pinned: set[str] = set()
    for mod in skills:
        cls = _skill_cls(mod)
        if cls is not None and getattr(cls, "always_load", False):
            pinned.add(_skill_name(mod))
    # context.pinned_skills
    from stato.core.astload import load_class
    ctx_path = stato_dir / "context.py"
    if ctx_path.exists():
        ctx = load_class(ctx_path.read_text())
        for n in (getattr(ctx, "pinned_skills", None) or []):
            pinned.add(str(n))
    return pinned


def _current_step(stato_dir: Path) -> dict | None:
    from stato.core.astload import load_class
    plan_path = stato_dir / "plan.py"
    if not plan_path.exists():
        return None
    plan = load_class(plan_path.read_text())
    steps = getattr(plan, "steps", None) if plan else None
    if not isinstance(steps, list):
        return None
    step = next((s for s in steps if isinstance(s, dict)
                 and s.get("status") in ("running", "pending")), None)
    if step is not None:
        step = dict(step)
        step["_objective"] = getattr(plan, "objective", "")
    return step


def assemble_workspace(stato_dir: Path, task: str | None = None,
                       budget: int | None = None, max_items: int = 6) -> WorkspaceView:
    """Assemble the working set for a task (or plan fallback). Stateless."""
    from stato.core.search import search_items
    from stato.core.summarize import render_summary, summarize_module

    stato_dir = Path(stato_dir)
    skills = _skill_modules(stato_dir)
    by_name = {_skill_name(m): m for m in skills}
    pinned = _pinned_names(stato_dir, skills)

    signal = "none"
    selected_names: list[str] = []

    if task and task.strip():
        signal = "task"
        items = [_skill_search_item(m) for m in skills]
        ranked = search_items(task, items, {"name": 3.0, "description": 2.0,
                                            "tags": 2.0, "lessons": 1.0})
        selected_names = [it["name"] for _score, it in ranked]
    else:
        step = _current_step(stato_dir)
        if step is not None:
            signal = "plan"
            used = step.get("skills_used")
            if isinstance(used, list) and used:
                selected_names = [str(u) for u in used]
            else:
                query = f"{step.get('action', '')} {step.get('_objective', '')}"
                items = [_skill_search_item(m) for m in skills]
                ranked = search_items(query, items, {"name": 3.0, "description": 2.0,
                                                     "tags": 2.0, "lessons": 1.0})
                selected_names = [it["name"] for _s, it in ranked]

    # Build active set: pins first (mandatory), then selected, capped.
    active_names: list[str] = []
    reasons: dict[str, str] = {}
    for n in pinned:
        if n in by_name and n not in active_names:
            active_names.append(n)
            reasons[n] = "pinned"
    for n in selected_names:
        if n in by_name and n not in active_names:
            active_names.append(n)
            reasons[n] = "task match" if signal == "task" else "plan step"

    # Cap: pins are mandatory; add up to max_items non-pins within budget.
    capped: list[str] = [n for n in active_names if reasons[n] == "pinned"]
    non_pins = [n for n in active_names if reasons[n] != "pinned"]
    used_chars = 0
    added = 0
    for n in non_pins:
        if added >= max_items:
            break
        summ = summarize_module(by_name[n]["full_path"].read_text())
        rendered = render_summary(summ) if summ else ""
        if budget is not None and capped and used_chars + len(rendered) > budget * 4:
            break
        used_chars += len(rendered)
        capped.append(n)
        added += 1

    active: list[WorkspaceItem] = []
    for n in capped:
        mod = by_name[n]
        summ = summarize_module(mod["full_path"].read_text())
        active.append(WorkspaceItem(
            name=n, rel_path=str(mod["rel_path"]), reason=reasons[n],
            summary=render_summary(summ) if summ else "",
        ))

    active_set = {i.name for i in active}
    index = []
    for mod in skills:
        n = _skill_name(mod)
        if n in active_set:
            continue
        cls = _skill_cls(mod)
        desc = ((getattr(cls, "description", "") or (cls.__doc__ or "")).strip().split("\n")[0]
                if cls else "")
        index.append({"name": n, "rel_path": str(mod["rel_path"]), "description": desc})

    return WorkspaceView(signal=signal, task=task, active=active, index=index, budget=budget)
