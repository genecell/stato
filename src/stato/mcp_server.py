"""Stato MCP server — expose validated agent state to any MCP client.

Resources are live views of .stato/ (read from disk per request, so an agent
always sees current state). Tools make the 7-pass compiler interactive: an
invalid write returns diagnostics in the tool result, so the model can
self-correct in the same turn. Prompts surface the crystallize templates as
slash commands.

Requires the mcp extra (pip install "stato[mcp]"). Import-guarded so the rest
of the package works without it.
"""
from __future__ import annotations

import json
from pathlib import Path


def build_server(project_dir: Path):
    """Construct the FastMCP server bound to a project directory."""
    from mcp.server.fastmcp import FastMCP

    stato_dir = project_dir / ".stato"
    mcp = FastMCP("stato")

    # --- Resources: live views of .stato/ ---------------------------------

    def _read_module(name: str) -> str:
        path = stato_dir / name
        if not path.exists():
            return f"(no {name} in this project)"
        return path.read_text()

    @mcp.resource("stato://context")
    def context_resource() -> str:
        """The project's context module (project, environment, conventions)."""
        return _read_module("context.py")

    @mcp.resource("stato://plan")
    def plan_resource() -> str:
        """The project's plan module (objective, steps, statuses)."""
        return _read_module("plan.py")

    @mcp.resource("stato://memory")
    def memory_resource() -> str:
        """The project's memory module (phase, reflection, known issues)."""
        return _read_module("memory.py")

    @mcp.resource("stato://resume")
    def resume_resource() -> str:
        """A generated recap of current project state (like `stato resume`)."""
        from stato.core.resume import generate_resume

        if not stato_dir.exists():
            return "(no .stato/ in this project)"
        return generate_resume(stato_dir, brief=False)

    @mcp.resource("stato://skills")
    def skills_index() -> str:
        """Index of available skills with descriptions."""
        from stato.core.composer import _discover_modules
        from stato.core.module import ModuleType

        if not stato_dir.exists():
            return "(no .stato/ in this project)"
        lines = []
        for m in _discover_modules(stato_dir):
            if m["module_type"] != ModuleType.SKILL:
                continue
            cls = m["namespace"].get(m["class_name"])
            name = getattr(cls, "name", m["class_name"])
            desc = getattr(cls, "description", "") or (cls.__doc__ or "").strip()
            lines.append(f"- {name} ({m['rel_path']}): {desc}")
        return "\n".join(lines) if lines else "(no skills)"

    @mcp.resource("stato://skills/{name}")
    def skill_resource(name: str) -> str:
        """Full source of a single skill by file stem."""
        path = stato_dir / "skills" / f"{name}.py"
        if not path.exists():
            return f"(no skill named {name})"
        return path.read_text()

    @mcp.resource("stato://skills/{name}/summary")
    def skill_summary_resource(name: str) -> str:
        """Compact summary + lessons index for a skill (progressive disclosure).

        Read this first; pull a specific lesson's full text with
        stato_get_skill_section instead of loading the whole skill.
        """
        from stato.core.summarize import render_summary, summarize_module

        path = stato_dir / "skills" / f"{name}.py"
        if not path.exists():
            return f"(no skill named {name})"
        summary = summarize_module(path.read_text())
        return render_summary(summary) if summary else "(could not summarize)"

    # --- Tools: the compiler, interactive ---------------------------------

    @mcp.tool()
    def stato_validate(source: str) -> str:
        """Validate a stato module's source. Returns diagnostics as JSON."""
        from stato.core.compiler import validate

        result = validate(source)
        return json.dumps(_result_to_dict(result), indent=2)

    @mcp.tool()
    def stato_write_module(rel_path: str, source: str) -> str:
        """Validate and write a module to .stato/<rel_path>.

        Returns diagnostics as JSON. On validation failure nothing is written
        and the errors are returned so you can fix and retry in one turn.
        """
        from stato.core.state_manager import write_module

        result = write_module(project_dir, rel_path, source)
        payload = _result_to_dict(result)
        payload["written"] = result.success
        payload["path"] = f".stato/{rel_path}" if result.success else None
        return json.dumps(payload, indent=2)

    @mcp.tool()
    def stato_update_plan_step(step_id: int, status: str = "", output: str = "") -> str:
        """Update one plan step's status and/or output, then validate+write.

        Ergonomic alternative to rewriting the whole plan module. Returns
        diagnostics as JSON; nothing is written if the result is invalid.
        """
        from stato.core.edits import EditError, set_plan_step
        from stato.core.state_manager import write_module

        plan_path = stato_dir / "plan.py"
        if not plan_path.exists():
            return json.dumps({"error": "no plan.py in this project"})
        try:
            new_source = set_plan_step(
                plan_path.read_text(), step_id,
                status=status or None, output=output or None,
            )
        except EditError as e:
            return json.dumps({"error": str(e)})
        result = write_module(project_dir, "plan.py", new_source)
        payload = _result_to_dict(result)
        payload["written"] = result.success
        return json.dumps(payload, indent=2)

    @mcp.tool()
    def stato_append_lesson(skill: str, lesson: str) -> str:
        """Append a lesson to a skill's lessons_learned, then validate+write.

        `skill` is the file stem under skills/ (e.g. "qc" for skills/qc.py).
        """
        from stato.core.edits import EditError, append_lesson
        from stato.core.state_manager import write_module

        rel = f"skills/{skill}.py"
        skill_path = stato_dir / rel
        if not skill_path.exists():
            return json.dumps({"error": f"no {rel} in this project"})
        try:
            new_source = append_lesson(skill_path.read_text(), lesson)
        except EditError as e:
            return json.dumps({"error": str(e)})
        result = write_module(project_dir, rel, new_source)
        payload = _result_to_dict(result)
        payload["written"] = result.success
        return json.dumps(payload, indent=2)

    @mcp.tool()
    def stato_workspace(task: str = "", budget: int = 0) -> str:
        """Assemble the working set of skills for your current TASK.

        Call this each turn with a short description of what you're doing now
        (e.g. "debugging GRN edge weights"). Returns the task-relevant skills as
        compact summaries plus a one-line index of the rest to pull on demand.
        With no task it falls back to the current plan step. This is the live,
        task-conditioned way to load only what you need.
        """
        from stato.core.workspace import assemble_workspace

        view = assemble_workspace(
            stato_dir, task=task or None, budget=budget or None,
        )
        return view.render()

    @mcp.tool()
    def stato_get_skill_section(skill: str, lesson_id: int) -> str:
        """Pull one lesson's full text from a skill by index (progressive
        disclosure). Read stato://skills/{skill}/summary first for the index."""
        from stato.core.summarize import get_skill_section

        path = stato_dir / "skills" / f"{skill}.py"
        if not path.exists():
            return json.dumps({"error": f"no skill named {skill}"})
        section = get_skill_section(path.read_text(), lesson_id)
        if section is None:
            return json.dumps({"error": f"no lesson {lesson_id} in {skill}"})
        return section

    @mcp.tool()
    def stato_resume(brief: bool = False) -> str:
        """Return a recap of current project state."""
        from stato.core.resume import generate_resume

        if not stato_dir.exists():
            return "(no .stato/ in this project)"
        return generate_resume(stato_dir, brief=brief)

    @mcp.tool()
    def stato_snapshot(output: str, sanitize: bool = False) -> str:
        """Export project state as a .stato archive.

        A privacy scan runs first; if it finds secrets and sanitize is False,
        the snapshot is refused and the findings are returned.
        """
        from stato.core.composer import snapshot as do_snapshot
        from stato.core.privacy import PrivacyScanner

        if not sanitize and stato_dir.exists():
            scanner = PrivacyScanner(ignore_file=project_dir / ".statoignore")
            findings = scanner.scan_directory(stato_dir)
            if findings:
                return json.dumps({
                    "refused": True,
                    "reason": "privacy scan found sensitive content; "
                              "call again with sanitize=true to redact",
                    "findings": [
                        {"file": f.file, "line": f.line, "description": f.description}
                        for f in findings[:50]
                    ],
                }, indent=2)

        out = do_snapshot(
            project_dir, name=Path(output).stem,
            output_path=Path(output), sanitize=sanitize,
        )
        return json.dumps({"written": True, "path": str(out)}, indent=2)

    @mcp.tool()
    def stato_registry_search(query: str) -> str:
        """Search the stato registry for shareable expertise packages."""
        from stato.core.config import load_config
        from stato.core.registry import fetch_registry_index, search_registry

        url = load_config(project_dir).registry_url
        try:
            packages = fetch_registry_index(url)
        except RuntimeError as e:
            return json.dumps({"error": str(e)})
        results = search_registry(query, packages)
        return json.dumps([
            {"name": p.name, "description": p.description, "version": p.version}
            for p in results
        ], indent=2)

    # --- Prompts ----------------------------------------------------------

    @mcp.prompt()
    def crystallize() -> str:
        """Prompt to capture agent expertise into .stato/ modules."""
        from stato.prompts import get_crystallize_prompt

        return get_crystallize_prompt()

    @mcp.prompt()
    def crystallize_web() -> str:
        """Prompt to capture expertise as a bundle (for web AI)."""
        from stato.prompts import get_web_crystallize_prompt

        return get_web_crystallize_prompt()

    return mcp


def _result_to_dict(result) -> dict:
    return {
        "success": result.success,
        "module_type": result.module_type.value if result.module_type else None,
        "class_name": result.class_name,
        "errors": [{"code": d.code, "message": d.message, "line": d.line}
                   for d in result.hard_errors],
        "warnings": [{"code": d.code, "message": d.message}
                     for d in result.auto_corrections],
        "advice": [{"code": d.code, "message": d.message} for d in result.advice],
    }


def run_server(project_dir: Path) -> None:
    """Run the MCP server over stdio."""
    server = build_server(project_dir)
    server.run()
