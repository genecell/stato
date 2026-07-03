"""Stato CLI — Click commands with Rich output."""
from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


COMMAND_SECTIONS = [
    ("State", ["init", "validate", "audit", "status", "resume", "crystallize",
               "find", "config", "doctor", "migrate-lessons"]),
    ("Composition", ["snapshot", "import", "import-bundle", "inspect", "slice",
                     "graft", "diff", "merge", "convert"]),
    ("Bridges & Hooks", ["bridge", "hooks", "mcp", "crystallize-transcript"]),
    ("Teams", ["team"]),
    ("Skill", ["skill"]),
    ("Sharing", ["registry"]),
]


class GroupedGroup(click.Group):
    """Group that renders --help commands in themed sections."""

    def format_commands(self, ctx, formatter):
        assigned = set()
        for section, names in COMMAND_SECTIONS:
            rows = []
            for name in names:
                cmd = self.get_command(ctx, name)
                if cmd is None or cmd.hidden:
                    continue
                rows.append((name, cmd.get_short_help_str(limit=60)))
                assigned.add(name)
            if rows:
                with formatter.section(section):
                    formatter.write_dl(rows)
        leftovers = [
            (name, self.get_command(ctx, name).get_short_help_str(limit=60))
            for name in self.list_commands(ctx)
            if name not in assigned and not self.get_command(ctx, name).hidden
        ]
        if leftovers:
            with formatter.section("Other"):
                formatter.write_dl(leftovers)


@click.group(cls=GroupedGroup)
@click.version_option(package_name="stato")
@click.option("-q", "--quiet", is_flag=True,
              help="Suppress non-essential output (rely on exit codes; --json still prints)")
def main(quiet):
    """Stato: Capture, validate, and transfer AI agent expertise."""
    # Always assign (not just when true) so quiet never leaks between
    # invocations that share a process (tests, the MCP server).
    console.quiet = quiet


# ---------------------------------------------------------------------------
# Core commands
# ---------------------------------------------------------------------------

@main.command()
@click.option("--mcp", "with_mcp", is_flag=True,
              help="Also write an .mcp.json entry for the stato MCP server")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def init(with_mcp, path):
    """Initialize a stato project."""
    from stato.core.state_manager import init_project

    project_dir = Path(path).resolve()
    init_project(project_dir)
    console.print(
        f"[green]Initialized stato project at "
        f"{project_dir / '.stato'}[/green]"
    )

    if with_mcp:
        added = _write_mcp_json(project_dir)
        if added:
            console.print("[green]Added stato server to .mcp.json[/green]")
        else:
            console.print("[yellow].mcp.json already has a stato server[/yellow]")


def _write_mcp_json(project_dir: Path) -> bool:
    """Merge a stato stdio server into .mcp.json. Returns True if added."""
    import json

    path = project_dir / ".mcp.json"
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError:
            data = {}
    servers = data.setdefault("mcpServers", {})
    if "stato" in servers:
        return False
    servers["stato"] = {"type": "stdio", "command": "stato", "args": ["mcp"]}
    path.write_text(json.dumps(data, indent=2) + "\n")
    return True


@main.command("validate")
@click.argument("target", type=click.Path(exists=True))
@click.option("--strict", is_flag=True, help="Promote auto-correction warnings to errors")
@click.option("--suppress", multiple=True, help="Diagnostic codes to hide (repeatable)")
@click.option("--error-code", "error_codes", multiple=True,
              help="Promote a specific code to an error (repeatable, e.g. -I006)")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output")
def validate_cmd(target, strict, suppress, error_codes, as_json):
    """Validate module(s). TARGET is a file or directory."""
    from stato.core.compiler import validate as compiler_validate
    from stato.core.config import load_config

    target_path = Path(target).resolve()
    cfg = load_config(Path.cwd())
    strict = strict or cfg.validate_strict
    suppress_codes = list(suppress) + cfg.validate_suppress
    promote_codes = list(error_codes) + cfg.validate_error_codes

    if target_path.is_file():
        files = [target_path]
    else:
        files = sorted(target_path.rglob("*.py"))
        files = [
            f for f in files
            if ".history" not in f.parts and not f.name.startswith("__")
        ]

    if not files:
        console.print("[yellow]No module files found.[/yellow]")
        return

    total_errors = 0
    json_files = []
    for f in files:
        source = f.read_text()
        result = compiler_validate(source, strict=strict, suppress=suppress_codes,
                                   error_codes=promote_codes)
        if as_json:
            json_files.append({
                "file": str(f),
                "success": result.success,
                "type": result.module_type.value if result.module_type else None,
                "class_name": result.class_name,
                "errors": [vars(d) for d in result.hard_errors],
                "warnings": [vars(d) for d in result.auto_corrections],
                "advice": [vars(d) for d in result.advice],
            })
        else:
            _print_validation_result(f, result)
        total_errors += len(result.hard_errors)

    if as_json:
        _echo_json({"files": json_files, "total_errors": total_errors})
        if total_errors:
            raise SystemExit(1)
        return

    console.print()
    if total_errors == 0:
        console.print(f"[green]All {len(files)} module(s) valid.[/green]")
    else:
        console.print(f"[red]{total_errors} error(s) found.[/red]")
        raise SystemExit(1)


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def status(as_json, path):
    """Show all modules, plan progress, and warnings."""
    from stato.core.composer import _discover_modules
    from stato.core.module import ModuleType
    from stato.modules.plan import PlanHelpers

    project_dir = Path(path).resolve()
    as_dir = project_dir / ".stato"
    if not as_dir.exists():
        console.print(
            "[red]No .stato/ directory found. "
            "Run 'stato init' first.[/red]"
        )
        raise SystemExit(1)

    modules = _discover_modules(as_dir)

    if as_json:
        from stato import __version__ as _v
        payload = {"stato_version": _v, "modules": [], "plans": []}
        for mod in modules:
            cls = (
                mod["namespace"].get(mod["class_name"])
                if mod.get("namespace") else None
            )
            payload["modules"].append({
                "path": str(mod["rel_path"]),
                "type": mod["module_type"].value,
                "class_name": mod["class_name"],
                "version": str(getattr(cls, "version", "")) if cls else "",
            })
        for pm in [m for m in modules if m["module_type"] == ModuleType.PLAN]:
            cls = pm["namespace"].get(pm["class_name"])
            if cls and hasattr(cls, "steps"):
                done, total = PlanHelpers.progress(cls.steps)
                next_s = PlanHelpers.next_step(cls.steps)
                payload["plans"].append({
                    "name": getattr(cls, "name", ""),
                    "objective": getattr(cls, "objective", ""),
                    "complete": done,
                    "total": total,
                    "next_step": next_s,
                })
        _echo_json(payload)
        return

    if not modules:
        console.print("[yellow]No modules found in .stato/[/yellow]")
        return

    from stato import __version__ as _v
    console.print(f"[dim]Stato: {_v}[/dim]")

    table = Table(title="Stato Modules")
    table.add_column("Module", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Class", style="green")
    table.add_column("Version", style="dim")

    for mod in modules:
        cls = (
            mod["namespace"].get(mod["class_name"])
            if mod.get("namespace")
            else None
        )
        version = getattr(cls, "version", "-") if cls else "-"
        table.add_row(
            str(mod["rel_path"]),
            mod["module_type"].value,
            mod["class_name"],
            str(version),
        )
    console.print(table)

    # Plan progress
    plan_mods = [m for m in modules if m["module_type"] == ModuleType.PLAN]
    for pm in plan_mods:
        cls = pm["namespace"].get(pm["class_name"])
        if cls and hasattr(cls, "steps"):
            done, total = PlanHelpers.progress(cls.steps)
            next_s = PlanHelpers.next_step(cls.steps)
            next_info = (
                f"Next: Step {next_s['id']} — {next_s['action']}"
                if next_s
                else "All done!"
            )
            console.print(Panel(
                f"Objective: {getattr(cls, 'objective', '?')}\n"
                f"Progress: {done}/{total} steps complete\n"
                f"{next_info}",
                title=f"Plan: {getattr(cls, 'name', '?')}",
                border_style="blue",
            ))


# ---------------------------------------------------------------------------
# Composition commands
# ---------------------------------------------------------------------------

@main.command()
@click.option("--name", required=True, help="Archive name")
@click.option("--template", is_flag=True, help="Reset runtime state")
@click.option("--module", "modules", multiple=True, help="Specific modules")
@click.option("--type", "types", multiple=True, help="Filter by module type")
@click.option("--exclude", multiple=True, help="Exclude types or modules")
@click.option("--description", default="", help="Description in manifest")
@click.option("--output", type=click.Path(), help="Output path")
@click.option("--sanitize", is_flag=True, help="Auto-replace detected secrets")
@click.option("--force", is_flag=True, help="Skip privacy scan")
@click.option("--dry-run", is_flag=True, help="Show what would be archived without writing")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def snapshot(name, template, modules, types, exclude, description, output,
             sanitize, force, dry_run, path):
    """Export agent state as .stato archive."""
    from stato.core.composer import snapshot as do_snapshot
    from stato.core.privacy import PrivacyScanner

    project_dir = Path(path).resolve()
    stato_dir = project_dir / ".stato"

    if dry_run:
        from stato.core.composer import _discover_modules, _filter_modules

        all_modules = _discover_modules(stato_dir)
        selected = _filter_modules(
            all_modules,
            list(modules) if modules else None,
            list(types) if types else None,
            list(exclude) if exclude else None,
        )
        out = Path(output) if output else project_dir / f"{name}.stato"
        console.print(f"[yellow]Dry run. Would archive to {out}:[/yellow]")
        for mod in selected:
            console.print(f"  [green]+[/green] {mod['rel_path']} ({mod['module_type'].value})")
        if template:
            console.print("  [dim](template reset would be applied)[/dim]")
        return

    if not force and stato_dir.exists():
        scanner = PrivacyScanner.from_config(
            project_dir, ignore_file=project_dir / ".statoignore",
        )
        findings = scanner.scan_directory(stato_dir)

        if findings:
            console.print(
                f"\n[yellow]Privacy scan found {len(findings)} item(s):[/yellow]\n"
            )

            if sanitize:
                # --sanitize flag passed, just show summary and proceed
                for f in findings:
                    console.print(f"  [red]{f.file}:{f.line}[/red] — {f.description}")
                    console.print(f"    Matched: [dim]{f.matched_text}[/dim]")
            else:
                # Group by category for cleaner display
                by_category = {}
                for f in findings:
                    by_category.setdefault(f.category, []).append(f)

                for category, items in by_category.items():
                    console.print(f"  [bold]{category}[/bold] ({len(items)} found)")
                    for item in items[:3]:
                        console.print(f"    {item.file}:{item.line} — {item.description}")
                        console.print(
                            f"    [dim]{item.matched_text}[/dim] → "
                            f"[green]{item.replacement}[/green]"
                        )
                    if len(items) > 3:
                        console.print(f"    [dim]... and {len(items) - 3} more[/dim]")

                console.print()

                # Interactive prompt
                choice = click.prompt(
                    "Choose action: [s]anitize / [r]eview / [f]orce / [c]ancel",
                    type=click.Choice(["s", "r", "f", "c"], case_sensitive=False),
                    default="s",
                    show_choices=False,
                )
                console.print()

                if choice == "c":
                    console.print("[yellow]Cancelled.[/yellow]")
                    raise SystemExit(0)
                elif choice == "f":
                    console.print(
                        "[yellow]Exporting WITHOUT sanitization. "
                        "Be careful sharing this archive.[/yellow]"
                    )
                elif choice == "r":
                    # Show full detail of all findings
                    console.print("[bold]Full review:[/bold]\n")
                    for f in findings:
                        console.print(f"  {f.file}:{f.line}")
                        console.print(f"    Found:   [red]{f.matched_text}[/red]")
                        console.print(f"    Replace: [green]{f.replacement}[/green]")
                        console.print(f"    Reason:  {f.description}")
                        console.print()

                    # Ask again after review
                    choice2 = click.prompt(
                        "Proceed with: [s]anitize / [f]orce / [c]ancel",
                        type=click.Choice(["s", "f", "c"], case_sensitive=False),
                        default="s",
                    )
                    if choice2 == "c":
                        console.print("[yellow]Cancelled.[/yellow]")
                        raise SystemExit(0)
                    elif choice2 == "f":
                        console.print(
                            "[yellow]Exporting WITHOUT sanitization.[/yellow]"
                        )
                    elif choice2 == "s":
                        sanitize = True
                elif choice == "s":
                    sanitize = True

    output_path = Path(output) if output else None
    archive = do_snapshot(
        project_dir,
        name=name,
        output_path=output_path,
        description=description,
        template=template,
        modules=list(modules) or None,
        types=list(types) or None,
        exclude=list(exclude) or None,
        sanitize=sanitize,
    )
    if sanitize:
        console.print(
            "[green]Secrets sanitized in snapshot (originals unchanged)[/green]"
        )
    console.print(f"[green]Created archive: {archive}[/green]")


@main.command("import")
@click.argument("archive", type=click.Path(exists=True))
@click.option("--module", help="Import specific module only")
@click.option("--type", "type_filter", help="Import modules of this type")
@click.option("--as", "rename_as", help="Rename imported module")
@click.option("--dry-run", is_flag=True, help="Preview only")
@click.option("--force", is_flag=True, help="Import even if checksum verification fails")
@click.option("--platform", help="Auto-generate bridge for platform")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def import_cmd(archive, module, type_filter, rename_as, dry_run, force, platform, path):
    """Import modules from .stato archive."""
    from stato.core.composer import (
        ArchiveIntegrityError,
        import_snapshot,
        verify_archive,
    )

    project_dir = Path(path).resolve()
    modules_filter = [module] if module else None
    types_filter = [type_filter] if type_filter else None

    integrity = verify_archive(Path(archive))
    if integrity["legacy"]:
        console.print(
            "[yellow]Legacy archive (pre-v1): no checksums to verify.[/yellow]"
        )

    try:
        imported = import_snapshot(
            project_dir,
            Path(archive),
            modules=modules_filter,
            types=types_filter,
            dry_run=dry_run,
            force=force,
        )
    except ArchiveIntegrityError as e:
        console.print(f"[red]{e}[/red]")
        console.print("[dim]Use --force to import anyway (not recommended).[/dim]")
        raise SystemExit(1) from e

    if dry_run:
        console.print("[yellow]Dry run. Would import:[/yellow]")
    for m in imported:
        console.print(f"  [green]+[/green] {m}")

    if not dry_run and not imported:
        console.print("[yellow]No modules imported.[/yellow]")

    if platform and not dry_run:
        from stato.bridge.claude_code import generate_bridge
        generate_bridge(project_dir, platform=platform, force=True)
        console.print(f"[green]Generated bridge for {platform}[/green]")


# ---------------------------------------------------------------------------
# Import-bundle command
# ---------------------------------------------------------------------------

@main.command("import-bundle")
@click.argument("bundle_path", type=click.Path(exists=True))
@click.option("--platform", type=click.Choice(["claude", "cursor", "codex", "generic", "all"]),
              default="claude", help="Generate bridge for this platform after import")
@click.option("--dry-run", is_flag=True, help="Parse and validate without writing files")
def import_bundle(bundle_path, platform, dry_run):
    """Import modules from a bundle file (generated by web AI).

    A bundle is a single Python file containing multiple stato modules.
    Use this to transfer expertise from web AI conversations (Claude.ai,
    Gemini, ChatGPT) into a coding agent project.

    Usage:
      stato import-bundle stato_bundle.py
      stato import-bundle stato_bundle.py --platform all
      stato import-bundle stato_bundle.py --dry-run
    """
    from stato.core.bundle import parse_bundle
    from stato.core.compiler import validate as compiler_validate
    from stato.core.state_manager import init_project, write_module

    bundle = Path(bundle_path)
    result = parse_bundle(bundle)

    if result.errors:
        for err in result.errors:
            console.print(f"[red]✗ {err}[/red]")
        raise SystemExit(1)

    # Summary of what was found
    console.print("\n[bold]Bundle contents:[/bold]")
    console.print(f"  Skills:  {len(result.skills)} ({', '.join(result.skills.keys()) if result.skills else 'none'})")
    console.print(f"  Plan:    {'yes' if result.plan else 'no'}")
    console.print(f"  Memory:  {'yes' if result.memory else 'no'}")
    console.print(f"  Context: {'yes' if result.context else 'no'}")

    if dry_run:
        console.print("\n[dim]Dry run — validating without writing...[/dim]")

    # Ensure stato is initialized
    project_dir = Path.cwd()
    stato_dir = project_dir / ".stato"
    if not stato_dir.exists():
        console.print("\n[yellow]No .stato/ found. Initializing...[/yellow]")
        if not dry_run:
            init_project(project_dir)

    # Write and validate each module
    success_count = 0
    fail_count = 0

    for skill_name, skill_source in result.skills.items():
        module_path = f"skills/{skill_name}.py"
        if dry_run:
            validation = compiler_validate(skill_source, expected_type="skill")
            status = "[green]✓ valid[/green]" if validation.success else f"[red]✗ {validation.hard_errors[0].message}[/red]"
            console.print(f"  {module_path}: {status}")
            if validation.success:
                success_count += 1
            else:
                fail_count += 1
        else:
            write_result = write_module(project_dir, module_path, skill_source)
            if write_result.success:
                console.print(f"  [green]✓[/green] {module_path}")
                success_count += 1
            else:
                console.print(f"  [red]✗[/red] {module_path}: {write_result.hard_errors[0].message}")
                fail_count += 1

    for module_type, source, filename in [
        ("plan", result.plan, "plan.py"),
        ("memory", result.memory, "memory.py"),
        ("context", result.context, "context.py"),
    ]:
        if source:
            if dry_run:
                validation = compiler_validate(source, expected_type=module_type)
                status = "[green]✓ valid[/green]" if validation.success else f"[red]✗ {validation.hard_errors[0].message}[/red]"
                console.print(f"  {filename}: {status}")
                if validation.success:
                    success_count += 1
                else:
                    fail_count += 1
            else:
                write_result = write_module(project_dir, filename, source)
                if write_result.success:
                    console.print(f"  [green]✓[/green] {filename}")
                    success_count += 1
                else:
                    console.print(f"  [red]✗[/red] {filename}: {write_result.hard_errors[0].message}")
                    fail_count += 1

    # Summary
    console.print(f"\n[bold]Result:[/bold] {success_count} imported, {fail_count} failed")

    if not dry_run and success_count > 0 and fail_count == 0:
        # Generate bridge
        from stato.bridge.claude_code import ClaudeCodeBridge
        from stato.bridge.codex import CodexBridge
        from stato.bridge.cursor import CursorBridge
        from stato.bridge.generic import GenericBridge

        PLATFORMS = {
            "claude": (ClaudeCodeBridge, "CLAUDE.md"),
            "cursor": (CursorBridge, ".cursorrules"),
            "codex": (CodexBridge, "AGENTS.md"),
            "generic": (GenericBridge, "README.stato.md"),
        }

        if platform == "all":
            targets = list(PLATFORMS.keys())
        else:
            targets = [platform]

        for name in targets:
            bridge_cls, filename = PLATFORMS[name]
            bridge_obj = bridge_cls(project_dir)
            bridge_obj.write(force=True)
            console.print(f"[green]✓ Generated {filename}[/green]")

        console.print("\n[bold]Done![/bold] Your coding agent now has expertise from the web AI conversation.")


@main.command()
@click.argument("archive", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output")
def inspect(archive, as_json):
    """Preview archive contents without importing."""
    from stato.core.composer import inspect_archive

    info = inspect_archive(Path(archive))
    if as_json:
        _echo_json(info)
        return
    integrity = info["integrity"]
    if integrity["legacy"]:
        integrity_str = "[yellow]legacy (pre-v1, no checksums)[/yellow]"
    elif integrity["ok"]:
        integrity_str = "[green]verified[/green]"
    else:
        bad = integrity["mismatches"] + integrity["missing"]
        integrity_str = f"[red]FAILED ({', '.join(bad)})[/red]"

    console.print(Panel(
        f"Name: {info['name']}\n"
        f"Created: {info['created']}\n"
        f"Format: v{info['format_version'] or '0 (legacy)'}\n"
        f"Integrity: {integrity_str}\n"
        f"Template: {info['template']}\n"
        f"Partial: {info['partial']}\n"
        f"Description: {info['description'] or '(none)'}",
        title="Archive Info",
    ))

    table = Table(title="Modules")
    table.add_column("Path")
    table.add_column("Type")
    table.add_column("Class")
    table.add_column("Valid")
    for md in info["module_details"]:
        valid_str = "[green]yes[/green]" if md["valid"] else "[red]no[/red]"
        table.add_row(md["path"], md["type"], md["class_name"], valid_str)
    console.print(table)


@main.command()
@click.option(
    "--module", "modules", multiple=True, required=True,
    help="Modules to extract",
)
@click.option("--with-deps", is_flag=True, help="Include dependency modules")
@click.option("--output", type=click.Path(), help="Output archive path")
@click.option("--name", default="", help="Archive name")
@click.option("--dry-run", is_flag=True, help="List selected modules without writing")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def slice(modules, with_deps, output, name, dry_run, path):
    """Extract specific modules from current project."""
    from stato.core.composer import slice_modules

    project_dir = Path(path).resolve()
    output_path = Path(output) if output else None

    if dry_run:
        from stato.core.composer import _discover_modules

        all_modules = _discover_modules(project_dir / ".stato")
        stems = {m.replace(".py", "") for m in modules}
        selected = [
            m for m in all_modules
            if str(m["rel_path"]).replace(".py", "") in stems
        ]
        console.print("[yellow]Dry run. Would slice:[/yellow]")
        for mod in selected:
            console.print(f"  [green]+[/green] {mod['rel_path']}")
        missing = stems - {
            str(m["rel_path"]).replace(".py", "") for m in selected
        }
        for m in sorted(missing):
            console.print(f"  [red]missing:[/red] {m}")
        return

    archive, warnings = slice_modules(
        project_dir,
        modules=list(modules),
        output_path=output_path,
        with_deps=with_deps,
        name=name,
    )
    for w in warnings:
        console.print(f"  [yellow]Warning:[/yellow] {w}")
    console.print(f"[green]Created slice: {archive}[/green]")


@main.command()
@click.argument("source", type=click.Path(exists=True))
@click.option("--module", help="Specific module from archive")
@click.option("--as", "rename_as", help="Rename to avoid conflict")
@click.option(
    "--on-conflict",
    type=click.Choice(["ask", "replace", "rename", "skip"]),
    default="ask",
)
@click.option("--dry-run", is_flag=True, help="Report what would be grafted without writing")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def graft(source, module, rename_as, on_conflict, dry_run, path):
    """Add module from external source."""
    from stato.core.composer import graft as do_graft

    project_dir = Path(path).resolve()
    result = do_graft(
        project_dir,
        Path(source),
        module=module,
        rename_as=rename_as,
        on_conflict=on_conflict,
        dry_run=dry_run,
    )
    if dry_run:
        console.print("[yellow]Dry run. Would graft:[/yellow]")
    if result.success:
        if not dry_run:
            console.print("[green]Graft successful.[/green]")
        for m in result.imported_modules:
            console.print(f"  [green]+[/green] {m}")
    else:
        console.print("[red]Graft has unresolved conflicts.[/red]")
    for c in result.conflicts:
        console.print(f"  [yellow]Conflict:[/yellow] {c}")
    for w in result.dependency_warnings:
        console.print(f"  [yellow]Dep warning:[/yellow] {w}")


# ---------------------------------------------------------------------------
# Bridge command
# ---------------------------------------------------------------------------

@main.command()
@click.option(
    "--platform", "platforms", multiple=True,
    help="Platform(s): agents, claude, cursor, copilot, gemini, generic, skill, "
         "cursor-legacy, all (codex = alias for agents). Default: config "
         "bridge.platforms (agents + claude). Repeatable.",
)
@click.option("--force", is_flag=True, help="Overwrite existing files without asking")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def bridge(platforms, force, path):
    """Generate platform bridge file(s).

    AGENTS.md ('agents') is the primary bridge — the cross-tool standard
    read by Codex, Cursor, Copilot, Zed, Gemini CLI and more. 'skill'
    exports an Agent Skills directory (.claude/skills/.../SKILL.md).
    """
    from stato.bridge.engine import write_bridge
    from stato.bridge.platforms import all_platform_names, resolve_platform
    from stato.core.config import load_config

    project_dir = Path(path).resolve()
    cfg = load_config(project_dir)

    targets: list[str] = []
    for p in platforms:
        if p == "all":
            targets.extend(all_platform_names())
        elif p == "auto":
            targets.extend(cfg.bridge_platforms)
        else:
            targets.append(p)
    if not targets:
        targets = list(cfg.bridge_platforms)
    # de-dupe, keep order
    targets = list(dict.fromkeys(targets))

    for name in targets:
        if name == "skill":
            from stato.bridge.skill_export import export_skill

            skill_path, action = export_skill(project_dir, force=force)
            rel = skill_path.relative_to(project_dir)
            if action == "exists":
                console.print(
                    f"[yellow]{rel} exists — use --force to overwrite[/yellow]"
                )
            else:
                console.print(f"[green]Generated {rel} (Agent Skills format)[/green]")
            continue

        spec = resolve_platform(name)
        if spec is None:
            console.print(f"[red]Unknown platform: {name}[/red]")
            console.print(
                f"[dim]Available: {', '.join(all_platform_names(include_legacy=True))}, skill[/dim]"
            )
            raise SystemExit(1)

        result_path, action = write_bridge(project_dir, spec, force=force)
        filename = spec.output_path
        if action == "cancelled":
            console.print(f"[yellow]Skipped {filename}[/yellow]")
        elif action == "appended":
            console.print(f"[green]Appended stato section to {filename}[/green]")
        elif action == "renamed":
            console.print(f"[green]Saved as {result_path.name}[/green]")
        else:
            console.print(f"[green]Generated {filename}[/green]")


# ---------------------------------------------------------------------------
# Hooks commands — compaction integration (Design A)
# ---------------------------------------------------------------------------

@main.group()
def hooks():
    """Install compaction hooks that auto-restore stato state (Design A).

    Wires PreCompact/SessionStart (and platform equivalents) so validated
    .stato/ state re-enters context after every compaction, on Claude Code,
    Codex CLI, and Gemini CLI.
    """
    pass


main.add_command(hooks)


@hooks.command("install")
@click.option("--platform", "platforms", multiple=True,
              type=click.Choice(["claude", "codex", "gemini", "all"]),
              help="Platform(s) to install for. Repeatable. Default: all.")
@click.option("--reminders", is_flag=True,
              help="Also add a Stop-hook nudge to crystallize (claude/codex)")
@click.option("--dry-run", is_flag=True, help="Show the config changes without writing")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def hooks_install(platforms, reminders, dry_run, path):
    """Install stato compaction hooks (merge-not-overwrite, idempotent)."""
    from stato.hooks.installers import apply_writes, plan_install

    project_dir = Path(path).resolve()
    targets = ["claude", "codex", "gemini"] if not platforms or "all" in platforms \
        else list(dict.fromkeys(platforms))

    for platform in targets:
        writes = plan_install(project_dir, platform, uninstall=False, reminders=reminders)
        if dry_run:
            console.print(f"\n[bold]{platform}[/bold] (dry run):")
            for w in writes:
                rel = w["path"]
                console.print(f"  would write {rel}")
            continue
        changed = apply_writes(writes)
        console.print(f"\n[bold]{platform}[/bold]:")
        for line in changed:
            console.print(f"  [green]{line}[/green]")

    if not dry_run:
        console.print(
            "\n[dim]Hooks active on next session. Verify with: stato hooks status[/dim]"
        )


@hooks.command("uninstall")
@click.option("--platform", "platforms", multiple=True,
              type=click.Choice(["claude", "codex", "gemini", "all"]),
              help="Platform(s). Repeatable. Default: all.")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def hooks_uninstall(platforms, path):
    """Remove stato compaction hooks (leaves other hooks untouched)."""
    from stato.hooks.installers import apply_writes, plan_install

    project_dir = Path(path).resolve()
    targets = ["claude", "codex", "gemini"] if not platforms or "all" in platforms \
        else list(dict.fromkeys(platforms))

    for platform in targets:
        writes = plan_install(project_dir, platform, uninstall=True)
        changed = apply_writes(writes)
        console.print(f"[bold]{platform}[/bold]: " + (
            ", ".join(changed) if changed else "nothing to remove"
        ))


@hooks.command("status")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def hooks_status(as_json, path):
    """Show which platforms have stato hooks installed."""
    from stato.hooks.installers import status as hook_status

    project_dir = Path(path).resolve()
    state = hook_status(project_dir)
    if as_json:
        _echo_json(state)
        return
    for platform, installed in state.items():
        mark = "[green]installed[/green]" if installed else "[dim]not installed[/dim]"
        console.print(f"  {platform:8} {mark}")


# Hidden hook payload commands — invoked by the host CLIs, read JSON on stdin.
@main.group("hook", hidden=True)
def hook_group():
    """Internal: hook payload commands invoked by host CLIs."""
    pass


@hook_group.command("pre-compact")
def hook_pre_compact():
    from stato.hooks.payloads import pre_compact

    raise SystemExit(pre_compact())


@hook_group.command("stop-reminder")
def hook_stop_reminder():
    from stato.hooks.payloads import stop_reminder

    raise SystemExit(stop_reminder())


@hook_group.command("session-start")
def hook_session_start():
    from stato.hooks.payloads import session_start

    raise SystemExit(session_start())


# ---------------------------------------------------------------------------
# Crystallize-transcript (experimental, Design C)
# ---------------------------------------------------------------------------

@main.command("crystallize-transcript", hidden=True)
@click.argument("transcript", type=click.Path(exists=True))
@click.option("--model", default=None, help="Model for headless extraction")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def crystallize_transcript(transcript, model, path):
    """EXPERIMENTAL (Design C): extract stato modules from a transcript via `claude -p`.

    Shells out to a headless Claude session to read a compaction transcript and
    write .stato/ modules through the stato CLI (so the compiler gates output).
    Not wired into hooks by default — it costs tokens and relies on an
    undocumented headless-from-hook path. Prototype only.
    """
    import shutil
    import subprocess

    if shutil.which("claude") is None:
        console.print("[red]`claude` CLI not found on PATH — Design C needs it.[/red]")
        raise SystemExit(1)

    project_dir = Path(path).resolve()
    prompt = (
        f"Read the transcript at {transcript}. Extract durable project state and "
        "write/update .stato/ modules by following .stato/prompts/crystallize.md. "
        "After writing, run `stato validate .stato/` and fix any errors."
    )
    cmd = ["claude", "-p", prompt]
    if model:
        cmd += ["--model", model]

    console.print("[yellow]EXPERIMENTAL: running headless crystallization...[/yellow]")
    try:
        subprocess.run(cmd, cwd=project_dir, check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Headless crystallization failed: {e}[/red]")
        raise SystemExit(1) from e


# ---------------------------------------------------------------------------
# Team assembly
# ---------------------------------------------------------------------------

@main.group()
def team():
    """Assemble expertise-scoped subagents from a team spec (.stato/team.toml)."""
    pass


main.add_command(team)


@team.command("assemble")
@click.argument("team_toml", required=False, type=click.Path())
@click.option("--format", "formats", multiple=True,
              type=click.Choice(["claude", "codex", "gemini", "sdk", "all"]),
              help="Output format(s). Repeatable. Default: claude.")
@click.option("--force", is_flag=True, help="Overwrite hand-written agent files too")
@click.option("--dry-run", is_flag=True, help="Show what would be written")
@click.option("--inline", is_flag=True,
              help="Embed full skill source (default: lessons index + pull-on-demand)")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def team_assemble(team_toml, formats, force, dry_run, inline, path):
    """Generate one subagent per role, each scoped to its skills.

    By default each subagent carries a lessons INDEX per skill and pulls the
    exact lesson it needs on demand (progressive disclosure — keeps subagents
    light). Use --inline to embed full skill source for environments without
    the stato MCP server. Handoffs render as prose; the orchestrator decides
    who runs when.
    """
    from stato.team import ALL_FORMATS, TeamSpecError, assemble

    project_dir = Path(path).resolve()
    fmts = ALL_FORMATS if "all" in formats else (list(dict.fromkeys(formats)) or ["claude"])
    team_path = Path(team_toml) if team_toml else None

    try:
        results = assemble(
            project_dir, team_path=team_path, formats=fmts,
            force=force, dry_run=dry_run, inline=inline,
        )
    except TeamSpecError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from e

    if not results:
        console.print("[yellow]No agents generated.[/yellow]")
        return

    for out_path, action in results:
        rel = out_path.relative_to(project_dir)
        if action == "skipped":
            console.print(f"[yellow]Skipped {rel} (hand-written; use --force)[/yellow]")
        elif action == "would-write":
            console.print(f"would write {rel}")
        else:
            console.print(f"[green]{action.capitalize()} {rel}[/green]")


# ---------------------------------------------------------------------------
# Skill — install the canonical "how to use stato" Agent Skill
# ---------------------------------------------------------------------------

@main.group()
def skill():
    """Install the stato Agent Skill so coding agents know how to use stato.

    This is the canonical "how to use stato" skill (distinct from
    `stato bridge --platform skill`, which exports a project's own expertise).
    """
    pass


main.add_command(skill)


@skill.command("install")
@click.option("--tool", "tools", multiple=True,
              type=click.Choice(["claude", "codex", "cursor", "gemini", "all"]),
              help="Target tool(s). Repeatable. Default: claude.")
@click.option("--user", is_flag=True,
              help="Install into your home config (all projects) instead of this one")
@click.option("--force", is_flag=True, help="Overwrite an existing non-stato file")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def skill_install(tools, user, force, path):
    """Write the stato Agent Skill into each tool's skills/ directory.

    Usage:
      stato skill install                 # .claude/skills/stato/
      stato skill install --tool all      # claude, codex, cursor, gemini
      stato skill install --tool gemini --user
    """
    from stato.skill_doc import all_tools, render_skill_md, skill_target_dir

    project_dir = Path(path).resolve()
    targets = all_tools() if "all" in tools else (list(dict.fromkeys(tools)) or ["claude"])
    content = render_skill_md()
    marker = "name: stato"

    for tool in targets:
        target_dir = skill_target_dir(tool, user, project_dir)
        out = target_dir / "SKILL.md"
        if out.exists() and not force and marker not in out.read_text():
            console.print(f"[yellow]Skipped {out} (not stato-owned; use --force)[/yellow]")
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        existed = out.exists()
        out.write_text(content)
        action = "Updated" if existed else "Installed"
        try:
            shown = out.relative_to(project_dir)
        except ValueError:
            shown = out
        console.print(f"[green]{action} {shown}[/green]")


@skill.command("show")
def skill_show():
    """Print the canonical stato Agent Skill (pipe it anywhere)."""
    from stato.skill_doc import render_skill_md

    click.echo(render_skill_md())


# ---------------------------------------------------------------------------
# MCP server command
# ---------------------------------------------------------------------------

@main.command("mcp")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def mcp_cmd(path):
    """Run the stato MCP server (stdio) exposing state as resources/tools/prompts.

    Register in .mcp.json:
      {"mcpServers": {"stato": {"type": "stdio", "command": "stato", "args": ["mcp"]}}}

    Requires the mcp extra: pip install "stato[mcp]"
    """
    try:
        from stato.mcp_server import run_server
    except ImportError:
        console.print(
            "[red]MCP support not installed.[/red] Install with: "
            "[bold]pip install \"stato[mcp]\"[/bold]"
        )
        raise SystemExit(1) from None

    run_server(Path(path).resolve())


# ---------------------------------------------------------------------------
# Convert command
# ---------------------------------------------------------------------------

@main.command()
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--format", "source_format",
              type=click.Choice(["claude", "cursor", "codex", "skillkit", "generic", "auto"]),
              default="auto", help="Source file format (auto-detects by default)")
@click.option("--dry-run", is_flag=True, help="Show what would be created without writing")
@click.option("--smart", is_flag=True,
              help="Output a crystallize prompt for AI-assisted conversion (better results)")
def convert(filepath, source_format, dry_run, smart):
    """Convert CLAUDE.md, .cursorrules, SKILL.md, or other files to stato modules.

    Migrates existing expertise files into validated stato format.

    Usage:
      stato convert CLAUDE.md
      stato convert .cursorrules --format cursor
      stato convert SKILL.md
      stato convert notes.md --format generic
      stato convert CLAUDE.md --smart
      stato convert CLAUDE.md --dry-run
    """
    from stato.core.converter import (
        SourceFormat,
        convert_file,
        generate_smart_convert_prompt,
    )
    from stato.core.state_manager import init_project, write_module

    source = Path(filepath)

    if smart:
        from rich.markdown import Markdown

        content = source.read_text()
        prompt = generate_smart_convert_prompt(content, source.name)
        console.print(Panel(
            Markdown(prompt),
            title="[bold]Smart Convert Prompt[/bold]",
            subtitle="Paste into Claude.ai / Gemini / ChatGPT, then: stato import-bundle output.py",
            border_style="cyan",
        ))
        return

    fmt = None
    if source_format != "auto":
        fmt = SourceFormat(source_format)

    result = convert_file(source, fmt)

    console.print(f"\n[bold]Detected format:[/bold] {result.source_format.value}")
    console.print(f"[bold]Skills found:[/bold] {len(result.skills)}" +
                  (f" ({', '.join(result.skills.keys())})" if result.skills else ""))
    console.print(f"[bold]Context:[/bold] {'yes' if result.context else 'no'}")
    console.print(f"[bold]Plan:[/bold] {'yes' if result.plan else 'no'}")

    if result.warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for w in result.warnings:
            console.print(f"  [yellow]![/yellow] {w}")

    if dry_run:
        console.print("\n[dim]Dry run -- no files written.[/dim]")
        return

    project_dir = Path.cwd()
    stato_dir = project_dir / ".stato"
    if not stato_dir.exists():
        console.print("\n[yellow]No .stato/ found. Initializing...[/yellow]")
        init_project(project_dir)

    success = 0
    fail = 0

    for skill_name, skill_source in result.skills.items():
        module_path = f"skills/{skill_name}.py"
        write_result = write_module(project_dir, module_path, skill_source)
        if write_result.success:
            console.print(f"  [green]+[/green] {module_path}")
            success += 1
        else:
            console.print(f"  [red]x[/red] {module_path}: {write_result.hard_errors[0].message}")
            fail += 1

    if result.context:
        write_result = write_module(project_dir, "context.py", result.context)
        if write_result.success:
            console.print("  [green]+[/green] context.py")
            success += 1
        else:
            console.print(f"  [red]x[/red] context.py: {write_result.hard_errors[0].message}")
            fail += 1

    if result.plan:
        write_result = write_module(project_dir, "plan.py", result.plan)
        if write_result.success:
            console.print("  [green]+[/green] plan.py")
            success += 1
        else:
            console.print(f"  [red]x[/red] plan.py: {write_result.hard_errors[0].message}")
            fail += 1

    console.print(f"\n[bold]Result:[/bold] {success} modules created, {fail} failed")

    if success > 0:
        console.print("\n[green]+[/green] Run [bold]stato status[/bold] to review, "
                      "[bold]stato bridge[/bold] to generate bridge files.")


# ---------------------------------------------------------------------------
# Merge command
# ---------------------------------------------------------------------------

@main.command()
@click.argument("left", type=click.Path(exists=True))
@click.argument("right", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output archive path (default: merged.stato)")
@click.option("--strategy",
              type=click.Choice(["union", "prefer-left", "prefer-right"]),
              default="union", help="Merge strategy for conflicts")
@click.option("--dry-run", is_flag=True, help="Show merge plan without writing")
def merge(left, right, output, strategy, dry_run):
    """Merge two .stato archives with conflict resolution.

    Combines modules from LEFT and RIGHT archives. Modules unique to one
    side are included directly. Overlapping modules are merged using the
    chosen strategy.

    Usage:
      stato merge a.stato b.stato
      stato merge a.stato b.stato -o combined.stato
      stato merge a.stato b.stato --strategy prefer-left
      stato merge a.stato b.stato --dry-run
    """
    import tempfile

    from stato.core.merger import (
        MergeStrategy,
        create_archive,
        extract_archive,
        merge_archives,
    )

    left_path = Path(left)
    right_path = Path(right)

    with tempfile.TemporaryDirectory() as tmpdir:
        left_dir = Path(tmpdir) / "left"
        right_dir = Path(tmpdir) / "right"

        extract_archive(left_path, left_dir)
        extract_archive(right_path, right_dir)

        strat = MergeStrategy(strategy)
        result = merge_archives(left_dir, right_dir, strat)

        # Report
        if result.left_only:
            console.print(f"[cyan]Left only ({len(result.left_only)}):[/cyan]")
            for m in result.left_only:
                console.print(f"  [green]+[/green] {m}")

        if result.right_only:
            console.print(f"[cyan]Right only ({len(result.right_only)}):[/cyan]")
            for m in result.right_only:
                console.print(f"  [green]+[/green] {m}")

        if result.merged:
            console.print(f"[cyan]Merged ({len(result.merged)}):[/cyan]")
            for m in result.merged:
                console.print(f"  [yellow]~[/yellow] {m}")

        if result.conflicts:
            console.print(f"\n[yellow]Conflicts ({len(result.conflicts)}):[/yellow]")
            for c in result.conflicts:
                console.print(
                    f"  {c.module_path} / {c.field}: "
                    f"{c.left_value} vs {c.right_value} "
                    f"[dim]({c.resolution})[/dim]"
                )

        total = len(result.modules)
        console.print(f"\n[bold]Total modules:[/bold] {total}")

        if dry_run:
            console.print("[dim]Dry run -- no archive written.[/dim]")
            return

        # Write merged archive
        merged_dir = Path(tmpdir) / "merged"
        merged_dir.mkdir()
        for rel_path, source in result.modules.items():
            target = merged_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source)

        out_path = Path(output) if output else Path("merged.stato")
        create_archive(merged_dir, out_path, name="merged")
        console.print(f"[green]Created merged archive: {out_path}[/green]")


# ---------------------------------------------------------------------------
# Registry commands
# ---------------------------------------------------------------------------

@main.group()
def registry():
    """Search and install shared expertise packages."""
    pass


main.add_command(registry)


@registry.command("search")
@click.argument("query")
@click.option("--registry-url", default=None, help="Custom registry URL")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output")
def registry_search(query, registry_url, as_json):
    """Search the stato registry for expertise packages.

    Usage:
      stato registry search "scrna"
      stato registry search "fastapi"
      stato registry search "python testing"
    """
    from stato.core.registry import fetch_registry_index, search_registry

    url = _registry_url(registry_url)

    try:
        packages = fetch_registry_index(url)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        console.print("[dim]Check your internet connection or try --registry-url[/dim]")
        raise SystemExit(1) from e

    results = search_registry(query, packages)

    if as_json:
        _echo_json({"query": query, "results": [vars(pkg) for pkg in results]})
        return

    if not results:
        console.print(f"No packages found matching '{query}'")
        console.print(f"[dim]Registry has {len(packages)} packages total[/dim]")
        return

    console.print(f"\n[bold]Found {len(results)} package(s):[/bold]\n")

    for pkg in results:
        tags_str = " ".join(f"[dim]#{t}[/dim]" for t in pkg.tags[:4])
        console.print(f"  [bold]{pkg.name}[/bold] v{pkg.version} by {pkg.author}")
        console.print(f"    {pkg.description}")
        console.print(f"    {pkg.modules} modules | {tags_str}")
        console.print()

    console.print("[dim]Install with: stato registry install <name>[/dim]")


@registry.command("install")
@click.argument("package_name")
@click.option("--registry-url", default=None, help="Custom registry URL")
def registry_install(package_name, registry_url):
    """Install an expertise package from the registry.

    Downloads the package and imports modules.

    Usage:
      stato registry install scrna-expert
    """
    import tempfile

    from stato.core.composer import import_snapshot
    from stato.core.registry import download_package, fetch_registry_index
    from stato.core.state_manager import init_project

    url = _registry_url(registry_url)

    try:
        packages = fetch_registry_index(url)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from e

    pkg = None
    for p in packages:
        if p.name == package_name or p.name == package_name.split("/")[-1]:
            pkg = p
            break

    if not pkg:
        console.print(f"[red]Package '{package_name}' not found in registry[/red]")
        console.print("[dim]Search with: stato registry search <query>[/dim]")
        raise SystemExit(1)

    console.print(f"\n[bold]Installing {pkg.name} v{pkg.version}[/bold]")
    console.print(f"  {pkg.description}")
    console.print(f"  Author: {pkg.author}")
    console.print(f"  Modules: {pkg.modules}")

    with tempfile.TemporaryDirectory() as tmp:
        console.print("\n  Downloading...", end="")
        archive_path = download_package(pkg, Path(tmp))
        console.print(" [green]done[/green]")

        stato_dir = Path.cwd() / ".stato"
        if not stato_dir.exists():
            console.print("  Initializing .stato/...", end="")
            init_project(Path.cwd())
            console.print(" [green]done[/green]")

        console.print("  Importing modules...", end="")
        imported = import_snapshot(Path.cwd(), archive_path)
        console.print(" [green]done[/green]")

    console.print(f"\n[green]Installed {pkg.name}[/green]")
    for m in imported:
        console.print(f"  [green]+[/green] {m}")
    console.print("  Run [bold]stato status[/bold] to see imported modules")
    console.print("  Run [bold]stato bridge[/bold] to generate bridge files")


@registry.command("list")
@click.option("--registry-url", default=None, help="Custom registry URL")
def registry_list(registry_url):
    """List all packages in the registry.

    Usage:
      stato registry list
    """
    from stato.core.registry import fetch_registry_index

    url = _registry_url(registry_url)

    try:
        packages = fetch_registry_index(url)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from e

    if not packages:
        console.print("Registry is empty.")
        return

    console.print(f"\n[bold]Stato Registry ({len(packages)} packages):[/bold]\n")

    for pkg in sorted(packages, key=lambda p: p.name):
        console.print(f"  [bold]{pkg.name:20}[/bold] v{pkg.version:8} {pkg.description}")

    console.print("\n[dim]Search: stato registry search <query>[/dim]")
    console.print("[dim]Install: stato registry install <name>[/dim]")


@registry.command("package")
@click.argument("archive", type=click.Path(exists=True))
@click.option("--url", default="", help="Public URL where the archive will be hosted")
@click.option("--author", default="", help="Author name for the entry")
def registry_package(archive, url, author):
    """Generate a registry index.toml entry for a .stato archive.

    Computes the sha256 checksum and prints a ready-to-PR entry for
    docs/registry/index.toml (or your private registry index).

    Usage:
      stato registry package my-expertise.stato --url https://... --author you
    """
    from stato.core.registry import make_index_entry

    entry = make_index_entry(Path(archive), url=url, author=author)
    console.print("\n[bold]Registry entry (add to index.toml):[/bold]\n")
    click.echo(entry)
    if not url:
        console.print(
            "[yellow]No --url given — replace the placeholder url before publishing.[/yellow]"
        )


# ---------------------------------------------------------------------------
# Diff command
# ---------------------------------------------------------------------------

@main.command()
@click.argument("target_a")
@click.argument("target_b", required=False)
@click.option("--brief", is_flag=True, help="Show only changed fields")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def diff(target_a, target_b, brief, as_json, path):
    """Compare modules or snapshots.

    One argument: current module vs last backup.
    Two .stato files: compare two archives.
    Two .py files: compare two modules.
    """
    from stato.core.differ import diff_modules, diff_snapshots, diff_vs_backup

    project_dir = Path(path).resolve()

    if target_b is None:
        # Single arg: compare vs backup
        diffs = diff_vs_backup(project_dir, target_a)
        if as_json:
            _echo_json({"mode": "backup", "target": target_a,
                        "diffs": [vars(d) for d in diffs]})
            return
        if not diffs:
            console.print("[yellow]No backup found for comparison.[/yellow]")
            return
        console.print(f"\n  [bold]{target_a}[/bold] — current vs backup\n")
        _print_field_diffs(diffs, brief)
    elif target_a.endswith(".stato") and target_b.endswith(".stato"):
        # Two archives
        result = diff_snapshots(Path(target_a), Path(target_b))
        if as_json:
            _echo_json({"mode": "snapshots", "a": target_a, "b": target_b, **result})
            return
        if result["added"]:
            console.print("[green]Added:[/green]")
            for m in result["added"]:
                console.print(f"  [green]+[/green] {m}")
        if result["removed"]:
            console.print("[red]Removed:[/red]")
            for m in result["removed"]:
                console.print(f"  [red]-[/red] {m}")
        if result["changed"]:
            console.print("[yellow]Changed:[/yellow]")
            for m in result["changed"]:
                console.print(f"  [yellow]~[/yellow] {m}")
        if not any(result.values()):
            console.print("[green]Archives are identical.[/green]")
    else:
        # Two module files
        source_a = Path(target_a).read_text()
        source_b = Path(target_b).read_text()
        diffs = diff_modules(source_a, source_b)
        if as_json:
            _echo_json({"mode": "modules", "a": target_a, "b": target_b,
                        "diffs": [vars(d) for d in diffs]})
            return
        console.print(f"\n  [bold]{target_a}[/bold] vs [bold]{target_b}[/bold]\n")
        _print_field_diffs(diffs, brief)


def _print_field_diffs(diffs, brief: bool) -> None:
    """Print field-level diffs with Rich formatting."""
    for d in diffs:
        if brief and not d.changed:
            continue
        if d.changed:
            console.print(
                f"  [red]{d.field}:[/red]  {d.value_a} [red]→[/red] {d.value_b}"
            )
        else:
            console.print(f"  [dim]{d.field}:[/dim]  {d.value_a}")


# ---------------------------------------------------------------------------
# Resume command
# ---------------------------------------------------------------------------

@main.command()
@click.option("--raw", is_flag=True, help="Plain text (for piping into a coding agent)")
@click.option("--brief", is_flag=True, help="One-paragraph summary only")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def resume(raw, brief, as_json, path):
    """Generate a recap of current project state for context restoration.

    Use after /compact or when starting a new session to quickly restore
    the agent's understanding of the project.

    Usage:
      stato resume              # formatted recap
      stato resume --raw        # plain text for pasting
      stato resume --brief      # one-paragraph summary
    """
    from stato.core.resume import generate_resume

    project_dir = Path(path).resolve()
    stato_dir = project_dir / ".stato"
    if not stato_dir.exists():
        console.print(
            "[red]No .stato/ directory found. "
            "Run 'stato init' first.[/red]"
        )
        raise SystemExit(1)

    text = generate_resume(stato_dir, brief=brief)

    if as_json:
        _echo_json({"brief": brief, "text": text})
        return

    if raw:
        click.echo(text)
    else:
        console.print(Panel(
            text,
            title="[bold]Project Resume[/bold]",
            border_style="cyan",
        ))


# ---------------------------------------------------------------------------
# Crystallize command
# ---------------------------------------------------------------------------

@main.command()
@click.option("--print", "print_prompt", is_flag=True, help="Print full prompt to terminal")
@click.option("--web", is_flag=True, help="Prompt template for web AI (Claude.ai, Gemini, ChatGPT)")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def crystallize(print_prompt, web, path):
    """Save a prompt for capturing agent expertise.

    Default: saves prompt to .stato/prompts/crystallize.md
    --print: also prints the full prompt to terminal
    --web:   prompt for web AI (prints to terminal, saves to crystallize_web.md)
    """
    from stato.prompts import get_crystallize_prompt, get_web_crystallize_prompt

    project_dir = Path(path).resolve()
    prompts_dir = project_dir / ".stato" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    if web:
        template = get_web_crystallize_prompt()
        save_path = prompts_dir / "crystallize_web.md"
        save_path.write_text(template)
        # Web AI can't read local files, so always print to terminal
        click.echo(template)
        console.print(f"\n[dim]Also saved to {save_path.relative_to(project_dir)}[/dim]")
    else:
        template = get_crystallize_prompt()
        save_path = prompts_dir / "crystallize.md"
        save_path.write_text(template)

        if print_prompt:
            click.echo(template)
        else:
            console.print(Panel(
                f"Crystallize prompt saved to [bold]{save_path.relative_to(project_dir)}[/bold]\n\n"
                "Ask your coding agent:\n"
                '  [cyan]"Read and follow .stato/prompts/crystallize.md"[/cyan]',
                title="[bold]Crystallize[/bold]",
                border_style="cyan",
            ))


# ---------------------------------------------------------------------------
# Find command — local expertise search
# ---------------------------------------------------------------------------

@main.command("find")
@click.argument("query")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def find_cmd(query, as_json, path):
    """Search local .stato modules by name, description, tags, and lessons.

    Usage:
      stato find "qc filtering"
      stato find "batch effect" --json
    """
    from stato.core.composer import _discover_modules
    from stato.core.search import search_items

    project_dir = Path(path).resolve()
    stato_dir = project_dir / ".stato"
    if not stato_dir.exists():
        console.print("[red]No .stato/ directory found. Run 'stato init' first.[/red]")
        raise SystemExit(1)

    items = []
    for mod in _discover_modules(stato_dir):
        cls = mod["namespace"].get(mod["class_name"]) if mod.get("namespace") else None
        structured = getattr(cls, "lessons", None) if cls else None
        lessons_text = getattr(cls, "lessons_learned", "") if cls else ""
        if isinstance(structured, list):
            lessons_text += " " + " ".join(
                str(entry.get("recommendation", "")) + " " + str(entry.get("condition", ""))
                for entry in structured if isinstance(entry, dict)
            )
        items.append({
            "path": str(mod["rel_path"]),
            "type": mod["module_type"].value,
            "name": getattr(cls, "name", mod["class_name"]) if cls else mod["class_name"],
            "description": (getattr(cls, "description", "") or (cls.__doc__ or "")) if cls else "",
            "tags": list(getattr(cls, "tags", []) or []) if cls else [],
            "lessons": lessons_text,
        })

    scored = search_items(query, items, weights={
        "name": 3.0, "description": 2.0, "tags": 2.0, "lessons": 1.0, "path": 1.0,
    })

    if as_json:
        _echo_json({
            "query": query,
            "results": [dict(item, score=round(score, 3)) for score, item in scored],
        })
        return

    if not scored:
        console.print(f"No modules match '{query}'.")
        return

    console.print(f"\n[bold]{len(scored)} match(es) for '{query}':[/bold]\n")
    for _score, item in scored:
        desc = item["description"].strip().split("\n")[0]
        console.print(
            f"  [bold]{item['name']}[/bold] [dim]({item['type']})[/dim] "
            f"— .stato/{item['path']}"
        )
        if desc:
            console.print(f"    {desc}")
    console.print()


# ---------------------------------------------------------------------------
# migrate-lessons — prose lessons_learned -> structured lessons
# ---------------------------------------------------------------------------

@main.command("migrate-lessons")
@click.argument("target", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Show which modules would change")
def migrate_lessons_cmd(target, dry_run):
    """Convert prose lessons_learned bullets into structured `lessons` entries.

    Structured lessons are individually addressable, which unlocks precise
    progressive disclosure (pull one lesson via MCP). Non-destructive: keeps
    the prose field. TARGET is a skill file or a .stato/ directory.
    """
    from stato.core.edits import migrate_lessons
    from stato.core.state_manager import StateManager

    target_path = Path(target).resolve()
    if target_path.is_file():
        files = [target_path]
        project_dir = target_path.parent.parent.parent  # skills/x.py -> project
    else:
        files = sorted(target_path.rglob("skills/*.py"))
        project_dir = target_path.parent

    changed = 0
    for f in files:
        if f.name.startswith("__"):
            continue
        src = f.read_text()
        new = migrate_lessons(src)
        if new != src:
            changed += 1
            if dry_run:
                console.print(f"  would migrate {f.name}")
            else:
                sm = StateManager(project_dir)
                rel = str(f.relative_to(project_dir / ".stato"))
                result = sm.write(rel, new)
                mark = "[green]migrated[/green]" if result.success else "[red]failed[/red]"
                console.print(f"  {mark} {f.name}")
    if changed == 0:
        console.print("[yellow]Nothing to migrate (no prose lessons found).[/yellow]")
    elif not dry_run:
        console.print(f"[green]Migrated {changed} skill(s).[/green]")


# ---------------------------------------------------------------------------
# Audit command — quality scoring
# ---------------------------------------------------------------------------

@main.command("audit")
@click.argument("target", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output")
@click.option("--min", "min_score", type=float, default=None,
              help="Exit 1 if any module scores below this (0-10)")
def audit_cmd(target, as_json, min_score):
    """Score module quality and list concrete gaps.

    TARGET is a module file or a .stato/ directory.

    Usage:
      stato audit .stato/
      stato audit .stato/skills/qc.py
      stato audit .stato/ --min 6      # gate for CI / before publishing
    """
    from stato.core.audit import audit_directory, audit_module

    target_path = Path(target).resolve()
    if target_path.is_file():
        reports = [audit_module(target_path.read_text(), target_path.name)]
        aggregate = reports[0].score
    else:
        reports, aggregate = audit_directory(target_path)

    if as_json:
        _echo_json({
            "aggregate": round(aggregate, 1),
            "modules": [r.to_dict() for r in reports],
        })
    else:
        for r in reports:
            color = "green" if r.score >= 7 else "yellow" if r.score >= 4 else "red"
            type_str = f" [dim]({r.module_type})[/dim]" if r.module_type else ""
            console.print(f"\n[bold]{r.path}[/bold]{type_str}  "
                          f"[{color}]{r.score:.1f}/10[/{color}]")
            for c in r.failed:
                console.print(f"  [yellow]✗[/yellow] {c.key}: {c.suggestion}")
            if not r.failed:
                console.print("  [green]✓ all checks pass[/green]")
        if len(reports) > 1:
            agg_color = "green" if aggregate >= 7 else "yellow" if aggregate >= 4 else "red"
            console.print(f"\n[bold]Aggregate: [{agg_color}]{aggregate:.1f}/10[/{agg_color}][/bold]")

    if min_score is not None:
        below = [r for r in reports if r.score < min_score]
        if below:
            if not as_json:
                console.print(
                    f"\n[red]{len(below)} module(s) below --min {min_score}[/red]"
                )
            raise SystemExit(1)


# ---------------------------------------------------------------------------
# Doctor — environment sanity check
# ---------------------------------------------------------------------------

@main.command("doctor")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def doctor_cmd(as_json, path):
    """Report the stato environment: binary path, version, project state, hooks.

    Useful when `stato` runs from a conda/venv bin/ that isn't on the default
    PATH — this shows exactly which stato is answering.
    """
    import shutil
    import sys

    from stato import __version__
    from stato.hooks.installers import status as hook_status

    project_dir = Path(path).resolve()
    stato_dir = project_dir / ".stato"
    resolved = shutil.which("stato") or sys.argv[0]

    info = {
        "version": __version__,
        "resolved_binary": resolved,
        "python": sys.executable,
        "project_dir": str(project_dir),
        "stato_dir_present": stato_dir.exists(),
        "modules": 0,
        "hooks": {},
        "mcp_available": False,
    }
    if stato_dir.exists():
        from stato.core.composer import _discover_modules
        info["modules"] = len(_discover_modules(stato_dir))
        info["hooks"] = hook_status(project_dir)
    try:
        import mcp  # noqa: F401
        info["mcp_available"] = True
    except ImportError:
        pass

    if as_json:
        _echo_json(info)
        return

    console.print(f"[bold]stato {info['version']}[/bold]")
    console.print(f"  binary:  {info['resolved_binary']}")
    console.print(f"  python:  {info['python']}")
    console.print(f"  project: {info['project_dir']}")
    if info["stato_dir_present"]:
        console.print(f"  .stato/: [green]present[/green] ({info['modules']} modules)")
        hooks = ", ".join(k for k, v in info["hooks"].items() if v) or "none"
        console.print(f"  hooks:   {hooks}")
    else:
        console.print("  .stato/: [yellow]not initialized[/yellow] (run stato init)")
    console.print(f"  mcp:     {'available' if info['mcp_available'] else 'not installed'}")
    console.print("\n[dim]Tip: stato installs a console-script into the active "
                  "environment's bin/. If `stato` isn't found, activate that env "
                  "or use the full path above.[/dim]")


# ---------------------------------------------------------------------------
# Config command
# ---------------------------------------------------------------------------

@main.command("config")
@click.option("--init", "init_target", type=click.Choice(["user", "project"]),
              default=None, help="Write a commented config template")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def config_cmd(init_target, path):
    """Show the effective configuration and where each value comes from."""
    from stato.core.config import (
        load_config,
        project_config_path,
        user_config_path,
        write_config_template,
    )

    project_dir = Path(path).resolve()

    if init_target:
        target = (
            user_config_path() if init_target == "user"
            else project_config_path(project_dir)
        )
        if write_config_template(target):
            console.print(f"[green]Wrote config template to {target}[/green]")
        else:
            console.print(f"[yellow]{target} already exists — not overwritten.[/yellow]")
        return

    try:
        cfg = load_config(project_dir)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from e

    table = Table(title="Effective Stato Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Source", style="dim")

    display = [
        ("registry.url", cfg.registry_url, "registry_url"),
        ("privacy.disable", ", ".join(cfg.privacy_disable) or "-", "privacy_disable"),
        ("privacy.extra_patterns", str(len(cfg.privacy_extra_patterns)) + " pattern(s)",
         "privacy_extra_patterns"),
        ("bridge.default", cfg.bridge_default, "bridge_default"),
        ("bridge.platforms", ", ".join(cfg.bridge_platforms), "bridge_platforms"),
        ("validate.strict", str(cfg.validate_strict), "validate_strict"),
        ("validate.suppress", ", ".join(cfg.validate_suppress) or "-", "validate_suppress"),
        ("history.keep", str(cfg.history_keep), "history_keep"),
        ("hooks.freshness_gate", str(cfg.hooks_freshness_gate), "hooks_freshness_gate"),
        ("plugins.enabled", str(cfg.plugins_enabled), "plugins_enabled"),
    ]
    for label, value, attr in display:
        table.add_row(label, value, cfg.sources.get(attr, "default"))
    console.print(table)

    console.print(f"\n[dim]user config:    {user_config_path()}[/dim]")
    console.print(f"[dim]project config: {project_config_path(project_dir)}[/dim]")
    console.print("[dim]Create one with: stato config --init user|project[/dim]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _registry_url(cli_flag, project_dir: Path | None = None) -> str:
    """Resolve registry URL: CLI flag > env/config > default."""
    if cli_flag:
        return cli_flag
    from stato.core.config import load_config

    return load_config(project_dir or Path.cwd()).registry_url


def _echo_json(payload) -> None:
    """Print machine-readable JSON (bypasses rich/quiet)."""
    import json

    click.echo(json.dumps(payload, indent=2, default=str))


# Plain-English hints appended to error diagnostics
E_CODE_HINTS = {
    "E001": "the file is not valid Python — check the reported line",
    "E002": "a stato module must contain exactly one class definition",
    "E003": "add the missing field as a class attribute with a literal value",
    "E004": "add the missing method to the class (skills need a run() method)",
    "E005": "the module could not be parsed into a class — check its structure",
    "E006": "the name exists but is not a method — define it with 'def'",
    "E007": "change the field's value to the expected type",
    "E008": "every step needs a unique id, and depends_on must reference existing ids",
    "E009": "your plan steps reference each other in a loop — break the cycle",
    "E010": "use one of the allowed step statuses",
    "E011": "set __stato_type__ to one of: skill, plan, memory, context, protocol",
    "E012": "skills_used on a step must be a list of skill name strings",
}


def _print_validation_result(filepath: Path, result) -> None:
    """Rich-formatted validation output."""
    status_str = "[green]PASS[/green]" if result.success else "[red]FAIL[/red]"
    type_str = f"  [dim]({result.module_type.value})[/dim]" if result.module_type else ""
    console.print(f"  {status_str} {filepath.name}{type_str}")

    for d in result.hard_errors:
        line_info = f" (line {d.line})" if d.line else ""
        console.print(f"    [red]{d.code}[/red] {d.message}{line_info}")
        hint = E_CODE_HINTS.get(d.code)
        if hint:
            console.print(f"      [dim]hint: {hint}[/dim]")
    for d in result.auto_corrections:
        console.print(
            f"    [yellow]{d.code}[/yellow] {d.message} [dim](auto-fixed)[/dim]"
        )
    for d in result.advice:
        console.print(f"    [blue]{d.code}[/blue] {d.message}")


