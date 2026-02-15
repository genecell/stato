"""
File and archive operations. Pure Python, no LLM.
Run after EVERY change: pytest tests/test_structural.py
"""
import ast
import zipfile
from pathlib import Path

import tomli

from stato.core.state_manager import init_project, write_module
from stato.core.composer import (
    snapshot,
    import_snapshot,
    inspect_archive,
    slice_modules,
    graft,
)
from stato.bridge.claude_code import generate_bridge
from tests.fixtures import (
    VALID_QC_SKILL,
    VALID_NORMALIZE_SKILL,
    VALID_CLUSTER_SKILL,
    VALID_PLAN,
    VALID_MEMORY,
    VALID_CONTEXT,
)


def _load_manifest(archive_path: Path) -> dict:
    """Load manifest.toml from archive."""
    with zipfile.ZipFile(archive_path) as zf:
        return tomli.loads(zf.read("manifest.toml").decode("utf-8"))


def _load_module(filepath: Path):
    """Exec a module file and return the primary class."""
    source = filepath.read_text()
    namespace = {}
    exec(source, namespace)
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            return namespace[node.name]
    return None


# --- Init ---

def test_init_creates_directory_structure(tmp_path):
    """stato init creates .stato/ with correct structure."""
    init_project(tmp_path)
    assert (tmp_path / ".stato").is_dir()
    assert (tmp_path / ".stato" / "skills").is_dir()
    assert (tmp_path / ".stato" / "prompts").is_dir()
    assert (tmp_path / ".stato" / "prompts" / "crystallize.md").is_file()


def test_init_writes_crystallize_prompt(tmp_path):
    """init writes crystallize.md with the prompt template."""
    init_project(tmp_path)
    content = (tmp_path / ".stato" / "prompts" / "crystallize.md").read_text()
    assert len(content) > 100
    assert "stato" in content.lower()
    assert "Step 1" in content
    assert "Step 7" in content


# --- Snapshot ---

def test_snapshot_creates_valid_archive(tmp_path):
    """Snapshot produces a zip with manifest and all modules."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    write_module(project, "plan.py", VALID_PLAN)
    write_module(project, "memory.py", VALID_MEMORY)

    archive = snapshot(project, name="test-export")

    assert archive.exists()
    assert zipfile.is_zipfile(archive)
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        assert "manifest.toml" in names
        assert "skills/qc.py" in names
        assert "plan.py" in names
        assert "memory.py" in names


def test_partial_snapshot_type_filter(tmp_path):
    """--type skill exports only skills."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    write_module(project, "plan.py", VALID_PLAN)
    write_module(project, "memory.py", VALID_MEMORY)

    archive = snapshot(project, name="skills-only", types=["skill"])
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        assert "skills/qc.py" in names
        assert "plan.py" not in names
        assert "memory.py" not in names


def test_partial_snapshot_exclude(tmp_path):
    """--exclude memory exports everything except memory."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    write_module(project, "plan.py", VALID_PLAN)
    write_module(project, "memory.py", VALID_MEMORY)

    archive = snapshot(project, name="no-memory", exclude=["memory"])
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        assert "skills/qc.py" in names
        assert "plan.py" in names
        assert "memory.py" not in names


def test_partial_snapshot_single_module(tmp_path):
    """--module skills/qc exports only that module."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    write_module(project, "skills/normalize.py", VALID_NORMALIZE_SKILL)

    archive = snapshot(project, name="qc-only", modules=["skills/qc"])
    manifest = _load_manifest(archive)
    assert manifest["partial"] is True
    assert "skills/qc.py" in manifest["included_modules"]
    assert "skills/normalize.py" not in manifest["included_modules"]


# --- Import ---

def test_import_roundtrip_preserves_content(tmp_path):
    """Snapshot -> import preserves module content exactly."""
    project_a = init_project(tmp_path / "a")
    write_module(project_a, "skills/qc.py", VALID_QC_SKILL)

    archive = snapshot(project_a, name="roundtrip")

    project_b = init_project(tmp_path / "b")
    import_snapshot(project_b, archive)

    original = (project_a / ".stato/skills/qc.py").read_text()
    imported = (project_b / ".stato/skills/qc.py").read_text()
    assert original == imported


def test_template_resets_plan_preserves_expertise(tmp_path):
    """Template snapshot resets plan steps but keeps skill lessons."""
    project_a = init_project(tmp_path / "a")
    write_module(project_a, "plan.py", VALID_PLAN)
    write_module(project_a, "skills/qc.py", VALID_QC_SKILL)

    archive = snapshot(project_a, name="template", template=True)

    project_b = init_project(tmp_path / "b")
    import_snapshot(project_b, archive)

    plan = _load_module(project_b / ".stato/plan.py")
    assert all(s["status"] == "pending" for s in plan.steps)
    assert "scran" in plan.decision_log  # expertise preserved

    qc = _load_module(project_b / ".stato/skills/qc.py")
    assert "FFPE" in qc.lessons_learned  # expertise preserved


def test_partial_import_single_module(tmp_path):
    """Import only one module from a full archive."""
    project_a = init_project(tmp_path / "a")
    write_module(project_a, "skills/qc.py", VALID_QC_SKILL)
    write_module(project_a, "skills/normalize.py", VALID_NORMALIZE_SKILL)
    write_module(project_a, "plan.py", VALID_PLAN)
    archive = snapshot(project_a, name="full")

    project_b = init_project(tmp_path / "b")
    import_snapshot(project_b, archive, modules=["skills/qc"])

    assert (project_b / ".stato/skills/qc.py").exists()
    assert not (project_b / ".stato/skills/normalize.py").exists()
    assert not (project_b / ".stato/plan.py").exists()


# --- Inspect ---

def test_inspect_shows_archive_contents(tmp_path):
    """Inspect command shows modules without importing."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    write_module(project, "plan.py", VALID_PLAN)
    archive = snapshot(project, name="inspectable")

    info = inspect_archive(archive)
    assert info["name"] == "inspectable"
    assert "skills/qc.py" in info["modules"]
    assert "plan.py" in info["modules"]


# --- Graft ---

def test_graft_conflict_detection(tmp_path):
    """Grafting same-named skill detects name collision."""
    project = init_project(tmp_path / "main")
    write_module(project, "skills/qc.py", VALID_QC_SKILL)

    other = init_project(tmp_path / "other")
    write_module(other, "skills/qc.py", VALID_CLUSTER_SKILL)
    archive = snapshot(other, name="other")

    result = graft(project, archive, module="skills/qc")
    assert result.has_conflict


# --- Slice ---

def test_slice_warns_missing_dependency(tmp_path):
    """Slicing module that depends on another warns about missing dep."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    write_module(project, "skills/normalize.py", VALID_NORMALIZE_SKILL)

    archive, warnings = slice_modules(
        project, modules=["skills/normalize"], with_deps=False,
    )
    assert any("qc" in w.lower() for w in warnings)


def test_slice_with_deps_includes_dependencies(tmp_path):
    """Slicing with --with-deps pulls in dependency modules."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    write_module(project, "skills/normalize.py", VALID_NORMALIZE_SKILL)

    archive, _ = slice_modules(
        project, modules=["skills/normalize"], with_deps=True,
    )
    with zipfile.ZipFile(archive) as zf:
        assert "skills/normalize.py" in zf.namelist()
        assert "skills/qc.py" in zf.namelist()


# --- Bridge ---

def test_bridge_generates_claude_md(tmp_path):
    """Bridge generator creates CLAUDE.md with skill summaries."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    write_module(project, "plan.py", VALID_PLAN)
    result_path, action = generate_bridge(project, platform="claude", force=True)

    assert action == "created"
    bridge_text = (tmp_path / "CLAUDE.md").read_text()
    assert "qc_filtering" in bridge_text
    assert "max_pct_mito" in bridge_text
    assert ".stato" in bridge_text


def test_bridge_token_efficiency(tmp_path):
    """Bridge stays under 800 tokens even with many skills."""
    project = init_project(tmp_path)
    for i in range(15):
        skill = f'''
class Skill{i}:
    name = "skill_{i}"
    version = "1.0.0"
    depends_on = []
    default_params = {{"param": {i}}}
    lessons_learned = "Lesson for skill {i}."
    @staticmethod
    def run(**kwargs): pass
'''
        write_module(project, f"skills/skill_{i}.py", skill)

    generate_bridge(project, platform="claude", force=True)
    bridge_text = (tmp_path / "CLAUDE.md").read_text()

    # ~4 chars per token for English
    estimated_tokens = len(bridge_text) / 4
    assert estimated_tokens < 800, (
        f"Bridge is ~{estimated_tokens:.0f} tokens with 15 skills. "
        f"Should stay under 800 as a lightweight index."
    )


# --- Cursor + Codex bridges ---

def test_cursor_bridge_generates_cursorrules(tmp_path):
    """Cursor bridge creates .cursorrules with skill content."""
    from stato.bridge.cursor import generate_bridge
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    generate_bridge(project, force=True)
    assert (tmp_path / ".cursorrules").exists()
    content = (tmp_path / ".cursorrules").read_text()
    assert "qc_filtering" in content


def test_codex_bridge_generates_agents_md(tmp_path):
    """Codex bridge creates AGENTS.md with skill content."""
    from stato.bridge.codex import generate_bridge
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    generate_bridge(project, force=True)
    assert (tmp_path / "AGENTS.md").exists()
    content = (tmp_path / "AGENTS.md").read_text()
    assert "qc_filtering" in content


def test_bridge_includes_memory_and_resume_rules(tmp_path):
    """Bridge working rules include memory.py reminder and stato resume hint."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    generate_bridge(project, platform="claude", force=True)

    bridge_text = (tmp_path / "CLAUDE.md").read_text()
    assert "memory.py" in bridge_text
    assert "stato resume" in bridge_text


def test_bridge_all_generates_all_platforms(tmp_path):
    """bridge --platform all generates all 4 platform files."""
    from click.testing import CliRunner
    from stato.cli import main

    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)

    runner = CliRunner()
    result = runner.invoke(main, ["bridge", "--platform", "all", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".cursorrules").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "README.stato.md").exists()


def test_bridge_marker_in_output(tmp_path):
    """Generated bridge files contain the stato marker."""
    from stato.bridge.base import STATO_MARKER

    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    generate_bridge(project, platform="claude", force=True)

    bridge_text = (tmp_path / "CLAUDE.md").read_text()
    assert STATO_MARKER in bridge_text


def test_bridge_overwrites_stato_generated_file(tmp_path):
    """Bridge silently overwrites a file it previously generated."""
    from stato.bridge.base import STATO_MARKER

    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)

    # First generation
    generate_bridge(project, platform="claude", force=True)
    assert (tmp_path / "CLAUDE.md").exists()

    # Second generation (should overwrite silently, no force needed)
    _, action = generate_bridge(project, platform="claude")
    assert action == "overwritten"
    assert STATO_MARKER in (tmp_path / "CLAUDE.md").read_text()


def test_bridge_detects_existing_non_stato_file(tmp_path):
    """check_existing_bridge detects a non-stato file."""
    from stato.bridge.base import check_existing_bridge, STATO_MARKER

    # Write a hand-crafted CLAUDE.md (no stato marker)
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My custom rules\nDo things my way.\n")

    # With force, should return 'overwrite'
    assert check_existing_bridge(claude_md, force=True) == "overwrite"

    # Verify the file does NOT contain the stato marker
    assert STATO_MARKER not in claude_md.read_text()

    # No file: should return 'create'
    nonexistent = tmp_path / "NONEXISTENT.md"
    assert check_existing_bridge(nonexistent) == "create"

    # Stato-generated file: should return 'overwrite'
    stato_file = tmp_path / "STATO.md"
    stato_file.write_text(f"<!-- {STATO_MARKER} -->\n# Content\n")
    assert check_existing_bridge(stato_file) == "overwrite"


def test_bridge_force_overwrites(tmp_path):
    """bridge --force overwrites non-stato files silently."""
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)

    # Write a hand-crafted CLAUDE.md
    (tmp_path / "CLAUDE.md").write_text("# My custom rules\n")

    _, action = generate_bridge(project, platform="claude", force=True)
    assert action == "overwritten"
    assert "qc_filtering" in (tmp_path / "CLAUDE.md").read_text()


# --- Crystallize ---

def test_crystallize_saves_to_file(tmp_path):
    """crystallize saves prompt to .stato/prompts/crystallize.md by default."""
    from click.testing import CliRunner
    from stato.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["crystallize", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "crystallize.md" in result.output
    assert "coding agent" in result.output.lower()
    # Full prompt should NOT be in output
    assert "Step 1" not in result.output
    # File should exist with prompt content
    saved = (tmp_path / ".stato" / "prompts" / "crystallize.md").read_text()
    assert "Step 1" in saved
    assert "stato" in saved.lower()


def test_crystallize_print_flag(tmp_path):
    """crystallize --print prints full prompt and saves to file."""
    from click.testing import CliRunner
    from stato.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["crystallize", "--print", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "Step 1" in result.output
    assert "stato" in result.output.lower()
    # File should also be saved
    saved = (tmp_path / ".stato" / "prompts" / "crystallize.md").read_text()
    assert "Step 1" in saved


def test_crystallize_web(tmp_path):
    """crystallize --web prints web prompt and saves to file."""
    from click.testing import CliRunner
    from stato.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["crystallize", "--web", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "stato_bundle.py" in result.output
    assert "SKILLS" in result.output
    assert "import-bundle" in result.output
    # Web file should be saved
    saved = (tmp_path / ".stato" / "prompts" / "crystallize_web.md").read_text()
    assert "SKILLS" in saved


def test_init_writes_web_crystallize_prompt(tmp_path):
    """init_project creates crystallize_web.md with the web prompt template."""
    from stato.core.state_manager import init_project

    init_project(tmp_path)
    web_prompt = (tmp_path / ".stato" / "prompts" / "crystallize_web.md").read_text()
    assert "stato_bundle.py" in web_prompt
    assert "SKILLS" in web_prompt
