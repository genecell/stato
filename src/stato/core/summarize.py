"""Summarize — a compact projection of a module for progressive disclosure.

Because stato modules are AST-parseable, a subagent doesn't need the whole
skill in context: it can carry a *skeleton* (docstring, method signatures,
params, tags) plus a **lessons index** (one line per lesson) and pull the exact
lesson it needs on demand. That turns a 20-30k-token skill into a few hundred
tokens without losing addressability — precise, structure-based retrieval, no
embeddings.

Lessons are indexed from structured `lessons = [...]` (data-model v2) when
present; otherwise from `lessons_learned` prose split on `- ` bullets, so it
degrades gracefully for older skills.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field

from stato.core.astload import load_class, safe_parse


@dataclass
class Lesson:
    id: int
    title: str          # one-line index entry
    text: str           # full lesson text (for on-demand pull)


@dataclass
class ModuleSummary:
    name: str
    module_type: str | None
    docstring: str
    signatures: list[str] = field(default_factory=list)
    params: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    lessons: list[Lesson] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "module_type": self.module_type,
            "docstring": self.docstring,
            "signatures": self.signatures,
            "params": self.params,
            "tags": self.tags,
            "lessons_index": [{"id": ln.id, "title": ln.title} for ln in self.lessons],
        }


def _method_signatures(class_node: ast.ClassDef) -> list[str]:
    sigs = []
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args if a.arg != "self"]
            if node.args.vararg:
                args.append(f"*{node.args.vararg.arg}")
            if node.args.kwarg:
                args.append(f"**{node.args.kwarg.arg}")
            ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
            sigs.append(f"{node.name}({', '.join(args)}){ret}")
    return sigs


def _extract_lessons(cls) -> list[Lesson]:
    lessons: list[Lesson] = []
    structured = getattr(cls, "lessons", None)
    if isinstance(structured, list):
        for i, entry in enumerate(structured):
            if isinstance(entry, dict):
                title = (entry.get("condition") or entry.get("recommendation")
                         or f"lesson {i}")
                text = "; ".join(f"{k}: {v}" for k, v in entry.items())
                lessons.append(Lesson(i, str(title)[:120], text))
        if lessons:
            return lessons
    # Fall back to prose bullets.
    prose = getattr(cls, "lessons_learned", "") or ""
    bullets, current = [], []
    for line in prose.splitlines():
        s = line.strip()
        if s.startswith("- "):
            if current:
                bullets.append("\n".join(current))
            current = [s[2:]]
        elif current:
            current.append(s)
    if current:
        bullets.append("\n".join(current))
    for i, b in enumerate(bullets):
        title = b.splitlines()[0] if b else f"lesson {i}"
        lessons.append(Lesson(i, title[:120], b))
    return lessons


def summarize_module(source: str) -> ModuleSummary | None:
    """Build a compact summary of a module. Returns None if it can't be parsed."""
    from stato.core.compiler import validate

    try:
        tree = safe_parse(source)
    except SyntaxError:
        return None
    class_node = next((n for n in tree.body if isinstance(n, ast.ClassDef)), None)
    if class_node is None:
        return None
    cls = load_class(source)
    if cls is None:
        return None

    result = validate(source)
    params = list((getattr(cls, "default_params", None) or {}).keys())
    return ModuleSummary(
        name=getattr(cls, "name", class_node.name),
        module_type=result.module_type.value if result.module_type else None,
        docstring=(cls.__doc__ or "").strip().split("\n")[0],
        signatures=_method_signatures(class_node),
        params=params,
        tags=list(getattr(cls, "tags", []) or []),
        lessons=_extract_lessons(cls),
    )


def render_summary(summary: ModuleSummary) -> str:
    """Compact text form of a summary (the ~few-hundred-token 'brief skill')."""
    lines = [f"### {summary.name} ({summary.module_type})"]
    if summary.docstring:
        lines.append(summary.docstring)
    if summary.signatures:
        lines.append("Methods: " + ", ".join(summary.signatures))
    if summary.params:
        lines.append("Params: " + ", ".join(summary.params))
    if summary.tags:
        lines.append("Tags: " + ", ".join(summary.tags))
    if summary.lessons:
        lines.append(f"Lessons index ({len(summary.lessons)}):")
        for ln in summary.lessons:
            lines.append(f"  [{ln.id}] {ln.title}")
        lines.append("Pull a lesson's full text on demand "
                     "(stato_get_skill_section / read the section).")
    return "\n".join(lines)


def get_skill_section(source: str, lesson_id: int) -> str | None:
    """Return the full text of one lesson by index, or None if absent."""
    summary = summarize_module(source)
    if summary is None:
        return None
    for ln in summary.lessons:
        if ln.id == lesson_id:
            return ln.text
    return None
