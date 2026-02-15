"""Stato CLI — Click commands with Rich output."""
from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@click.group()
@click.version_option(version="0.5.0")
def main():
    """Stato: Capture, validate, and transfer AI agent expertise."""
    pass


# ---------------------------------------------------------------------------
# Core commands
# ---------------------------------------------------------------------------

@main.command()
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def init(path):
    """Initialize a stato project."""
    from stato.core.state_manager import init_project

    project_dir = Path(path).resolve()
    init_project(project_dir)
    console.print(
        f"[green]Initialized stato project at "
        f"{project_dir / '.stato'}[/green]"
    )


@main.command("validate")
@click.argument("target", type=click.Path(exists=True))
def validate_cmd(target):
    """Validate module(s). TARGET is a file or directory."""
    from stato.core.compiler import validate as compiler_validate

    target_path = Path(target).resolve()

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
    for f in files:
        source = f.read_text()
        result = compiler_validate(source)
        _print_validation_result(f, result)
        total_errors += len(result.hard_errors)

    console.print()
    if total_errors == 0:
        console.print(f"[green]All {len(files)} module(s) valid.[/green]")
    else:
        console.print(f"[red]{total_errors} error(s) found.[/red]")
        raise SystemExit(1)


@main.command()
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def status(path):
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

    if not modules:
        console.print("[yellow]No modules found in .stato/[/yellow]")
        return

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
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def snapshot(name, template, modules, types, exclude, description, output,
             sanitize, force, path):
    """Export agent state as .stato archive."""
    from stato.core.composer import snapshot as do_snapshot
    from stato.core.privacy import PrivacyScanner

    project_dir = Path(path).resolve()
    stato_dir = project_dir / ".stato"

    if not force and stato_dir.exists():
        scanner = PrivacyScanner(
            ignore_file=project_dir / ".statoignore",
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
@click.option("--platform", help="Auto-generate bridge for platform")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def import_cmd(archive, module, type_filter, rename_as, dry_run, platform, path):
    """Import modules from .stato archive."""
    from stato.core.composer import import_snapshot

    project_dir = Path(path).resolve()
    modules_filter = [module] if module else None
    types_filter = [type_filter] if type_filter else None
    imported = import_snapshot(
        project_dir,
        Path(archive),
        modules=modules_filter,
        types=types_filter,
        dry_run=dry_run,
    )

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
    console.print(f"\n[bold]Bundle contents:[/bold]")
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
        from stato.bridge.cursor import CursorBridge
        from stato.bridge.codex import CodexBridge
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

        console.print(f"\n[bold]Done![/bold] Your coding agent now has expertise from the web AI conversation.")


@main.command()
@click.argument("archive", type=click.Path(exists=True))
def inspect(archive):
    """Preview archive contents without importing."""
    from stato.core.composer import inspect_archive

    info = inspect_archive(Path(archive))
    console.print(Panel(
        f"Name: {info['name']}\n"
        f"Created: {info['created']}\n"
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
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def slice(modules, with_deps, output, name, path):
    """Extract specific modules from current project."""
    from stato.core.composer import slice_modules

    project_dir = Path(path).resolve()
    output_path = Path(output) if output else None
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
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def graft(source, module, rename_as, on_conflict, path):
    """Add module from external source."""
    from stato.core.composer import graft as do_graft

    project_dir = Path(path).resolve()
    result = do_graft(
        project_dir,
        Path(source),
        module=module,
        rename_as=rename_as,
        on_conflict=on_conflict,
    )
    if result.success:
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
    "--platform",
    type=click.Choice(["claude", "cursor", "codex", "generic", "auto", "all"]),
    default="auto",
)
@click.option("--force", is_flag=True, help="Overwrite existing files without asking")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def bridge(platform, force, path):
    """Generate platform bridge file."""
    from stato.bridge.claude_code import ClaudeCodeBridge
    from stato.bridge.cursor import CursorBridge
    from stato.bridge.codex import CodexBridge
    from stato.bridge.generic import GenericBridge

    PLATFORMS = {
        "claude": (ClaudeCodeBridge, "CLAUDE.md"),
        "cursor": (CursorBridge, ".cursorrules"),
        "codex": (CodexBridge, "AGENTS.md"),
        "generic": (GenericBridge, "README.stato.md"),
    }

    project_dir = Path(path).resolve()

    if platform == "auto":
        targets = ["claude"]
    elif platform == "all":
        targets = list(PLATFORMS.keys())
    else:
        targets = [platform]

    for name in targets:
        bridge_cls, filename = PLATFORMS[name]
        bridge_obj = bridge_cls(project_dir)
        result_path, action = bridge_obj.write(force=force)
        if action == "cancelled":
            console.print(f"[yellow]Skipped {filename}[/yellow]")
        elif action == "appended":
            console.print(f"[green]Appended stato section to {filename}[/green]")
        elif action == "renamed":
            console.print(f"[green]Saved as {result_path.name}[/green]")
        else:
            console.print(f"[green]Generated {filename}[/green]")


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
        SourceFormat, convert_file, generate_smart_convert_prompt,
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
        console.print(f"\n[yellow]Warnings:[/yellow]")
        for w in result.warnings:
            console.print(f"  [yellow]![/yellow] {w}")

    if dry_run:
        console.print(f"\n[dim]Dry run -- no files written.[/dim]")
        return

    project_dir = Path.cwd()
    stato_dir = project_dir / ".stato"
    if not stato_dir.exists():
        console.print(f"\n[yellow]No .stato/ found. Initializing...[/yellow]")
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
            console.print(f"  [green]+[/green] context.py")
            success += 1
        else:
            console.print(f"  [red]x[/red] context.py: {write_result.hard_errors[0].message}")
            fail += 1

    if result.plan:
        write_result = write_module(project_dir, "plan.py", result.plan)
        if write_result.success:
            console.print(f"  [green]+[/green] plan.py")
            success += 1
        else:
            console.print(f"  [red]x[/red] plan.py: {write_result.hard_errors[0].message}")
            fail += 1

    console.print(f"\n[bold]Result:[/bold] {success} modules created, {fail} failed")

    if success > 0:
        console.print(f"\n[green]+[/green] Run [bold]stato status[/bold] to review, "
                      f"[bold]stato bridge[/bold] to generate bridge files.")


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
        MergeStrategy, extract_archive, create_archive, merge_archives,
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
def registry_search(query, registry_url):
    """Search the stato registry for expertise packages.

    Usage:
      stato registry search "scrna"
      stato registry search "fastapi"
      stato registry search "python testing"
    """
    from stato.core.registry import (
        DEFAULT_REGISTRY, fetch_registry_index, search_registry,
    )

    url = registry_url or DEFAULT_REGISTRY

    try:
        packages = fetch_registry_index(url)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        console.print("[dim]Check your internet connection or try --registry-url[/dim]")
        raise SystemExit(1)

    results = search_registry(query, packages)

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

    console.print(f"[dim]Install with: stato registry install <name>[/dim]")


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

    from stato.core.registry import (
        DEFAULT_REGISTRY, fetch_registry_index, download_package,
    )
    from stato.core.composer import import_snapshot
    from stato.core.state_manager import init_project

    url = registry_url or DEFAULT_REGISTRY

    try:
        packages = fetch_registry_index(url)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    pkg = None
    for p in packages:
        if p.name == package_name or p.name == package_name.split("/")[-1]:
            pkg = p
            break

    if not pkg:
        console.print(f"[red]Package '{package_name}' not found in registry[/red]")
        console.print(f"[dim]Search with: stato registry search <query>[/dim]")
        raise SystemExit(1)

    console.print(f"\n[bold]Installing {pkg.name} v{pkg.version}[/bold]")
    console.print(f"  {pkg.description}")
    console.print(f"  Author: {pkg.author}")
    console.print(f"  Modules: {pkg.modules}")

    with tempfile.TemporaryDirectory() as tmp:
        console.print(f"\n  Downloading...", end="")
        archive_path = download_package(pkg, Path(tmp))
        console.print(f" [green]done[/green]")

        stato_dir = Path.cwd() / ".stato"
        if not stato_dir.exists():
            console.print(f"  Initializing .stato/...", end="")
            init_project(Path.cwd())
            console.print(f" [green]done[/green]")

        console.print(f"  Importing modules...", end="")
        imported = import_snapshot(Path.cwd(), archive_path)
        console.print(f" [green]done[/green]")

    console.print(f"\n[green]Installed {pkg.name}[/green]")
    for m in imported:
        console.print(f"  [green]+[/green] {m}")
    console.print(f"  Run [bold]stato status[/bold] to see imported modules")
    console.print(f"  Run [bold]stato bridge[/bold] to generate bridge files")


@registry.command("list")
@click.option("--registry-url", default=None, help="Custom registry URL")
def registry_list(registry_url):
    """List all packages in the registry.

    Usage:
      stato registry list
    """
    from stato.core.registry import DEFAULT_REGISTRY, fetch_registry_index

    url = registry_url or DEFAULT_REGISTRY

    try:
        packages = fetch_registry_index(url)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    if not packages:
        console.print("Registry is empty.")
        return

    console.print(f"\n[bold]Stato Registry ({len(packages)} packages):[/bold]\n")

    for pkg in sorted(packages, key=lambda p: p.name):
        console.print(f"  [bold]{pkg.name:20}[/bold] v{pkg.version:8} {pkg.description}")

    console.print(f"\n[dim]Search: stato registry search <query>[/dim]")
    console.print(f"[dim]Install: stato registry install <name>[/dim]")


# ---------------------------------------------------------------------------
# Diff command
# ---------------------------------------------------------------------------

@main.command()
@click.argument("target_a")
@click.argument("target_b", required=False)
@click.option("--brief", is_flag=True, help="Show only changed fields")
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def diff(target_a, target_b, brief, path):
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
        if not diffs:
            console.print("[yellow]No backup found for comparison.[/yellow]")
            return
        console.print(f"\n  [bold]{target_a}[/bold] — current vs backup\n")
        _print_field_diffs(diffs, brief)
    elif target_a.endswith(".stato") and target_b.endswith(".stato"):
        # Two archives
        result = diff_snapshots(Path(target_a), Path(target_b))
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
@click.option("--path", default=".", type=click.Path(), help="Project directory")
def resume(raw, brief, path):
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
# Helpers
# ---------------------------------------------------------------------------

def _print_validation_result(filepath: Path, result) -> None:
    """Rich-formatted validation output."""
    status_str = "[green]PASS[/green]" if result.success else "[red]FAIL[/red]"
    type_str = f"  [dim]({result.module_type.value})[/dim]" if result.module_type else ""
    console.print(f"  {status_str} {filepath.name}{type_str}")

    for d in result.hard_errors:
        line_info = f" (line {d.line})" if d.line else ""
        console.print(f"    [red]{d.code}[/red] {d.message}{line_info}")
    for d in result.auto_corrections:
        console.print(
            f"    [yellow]{d.code}[/yellow] {d.message} [dim](auto-fixed)[/dim]"
        )
    for d in result.advice:
        console.print(f"    [blue]{d.code}[/blue] {d.message}")


