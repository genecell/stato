# Stato: Automated Pre-Launch Integration Tests

Convert the pre-launch testing checklist into automated pytest integration tests. All tests go in a single file: `tests/test_integration.py`. Mark every test with `@pytest.mark.integration`.

Read `docs/prompt/STATO_PRELAUNCH_TESTING.md` for the full manual checklist. This prompt tells you how to automate each one.

---

## Setup

### Register the integration marker

In `pyproject.toml` (or `pytest.ini` / `conftest.py`), register the marker:

```toml
[tool.pytest.ini_options]
markers = [
    "agent: behavioral tests requiring Claude Code (deselect with '-m not agent')",
    "integration: pre-launch integration tests (slower, create temp dirs)",
]
```

### Test file structure

```python
# tests/test_integration.py
"""
Pre-launch integration tests for stato.

These tests verify end-to-end workflows by running actual CLI commands
and checking outputs. They are slower than unit tests because they
create real directories, write files, and invoke subprocesses.

Run with: pytest tests/test_integration.py -v
Skip with: pytest tests/ -m "not integration"
"""

import pytest
import subprocess
import os
from pathlib import Path

pytestmark = pytest.mark.integration


def run_stato(args: list[str], cwd: str | Path | None = None, 
              expect_fail: bool = False) -> subprocess.CompletedProcess:
    """Run a stato CLI command and return the result.
    
    Args:
        args: Command arguments (without 'stato' prefix)
        cwd: Working directory
        expect_fail: If True, don't assert returncode==0
    
    Returns:
        CompletedProcess with stdout and stderr
    """
    result = subprocess.run(
        ["stato"] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    if not expect_fail:
        assert result.returncode == 0, (
            f"stato {' '.join(args)} failed:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result
```

---

## Tests to Implement

### Test 1: All CLI Commands Register

```python
def test_all_commands_respond_to_help():
    """Every stato CLI command responds to --help without error."""
    commands = [
        ["--help"],
        ["init", "--help"],
        ["crystallize", "--help"],
        ["validate", "--help"],
        ["status", "--help"],
        ["snapshot", "--help"],
        ["import", "--help"],
        ["inspect", "--help"],
        ["slice", "--help"],
        ["graft", "--help"],
        ["bridge", "--help"],
        ["diff", "--help"],
        ["resume", "--help"],
        ["convert", "--help"],
        ["merge", "--help"],
        ["registry", "--help"],
        ["registry", "search", "--help"],
        ["registry", "install", "--help"],
        ["registry", "list", "--help"],
    ]
    for cmd in commands:
        result = run_stato(cmd)
        assert result.returncode == 0, f"stato {' '.join(cmd)} failed"
```

### Test 2: Core Workflow

```python
def test_core_workflow(tmp_path):
    """init -> crystallize -> status -> bridge runs without error."""
    # Init
    result = run_stato(["init"], cwd=tmp_path)
    assert (tmp_path / ".stato").is_dir()
    assert (tmp_path / ".stato" / "skills").is_dir()
    
    # Crystallize (both modes)
    result = run_stato(["crystallize"], cwd=tmp_path)
    assert len(result.stdout) > 0  # Should print a prompt
    
    result = run_stato(["crystallize", "--web"], cwd=tmp_path)
    assert len(result.stdout) > 0
    
    # Status on empty project (should not crash)
    result = run_stato(["status"], cwd=tmp_path)
    
    # Bridge on empty project (should not crash)
    result = run_stato(["bridge", "--platform", "claude"], cwd=tmp_path)
```

### Test 3: Module Validation

```python
VALID_SKILL = '''
class TestSkill:
    """A test skill."""
    name = "test_skill"
    version = "1.0.0"
    depends_on = ["pytest"]
    default_params = {"timeout": 30, "retries": 3}
    lessons_learned = """
    - Always set a timeout
    - Retry transient failures
    """
    @staticmethod
    def run(**kwargs): pass
'''

INVALID_SKILL = '''
class BadSkill:
    x = 1
'''


def test_valid_module_passes_validation(tmp_path):
    """A properly structured skill passes validation."""
    run_stato(["init"], cwd=tmp_path)
    skill_path = tmp_path / ".stato" / "skills" / "test_skill.py"
    skill_path.write_text(VALID_SKILL)
    
    result = run_stato(["validate", ".stato/"], cwd=tmp_path)
    # Should not report hard errors
    assert "error" not in result.stdout.lower() or "0 error" in result.stdout.lower()


def test_invalid_module_caught(tmp_path):
    """A module missing required fields is caught by validation."""
    run_stato(["init"], cwd=tmp_path)
    skill_path = tmp_path / ".stato" / "skills" / "bad.py"
    skill_path.write_text(INVALID_SKILL)
    
    result = run_stato(["validate", ".stato/"], cwd=tmp_path, expect_fail=True)
    # Should report errors (either in stdout or nonzero exit)
    output = result.stdout + result.stderr
    assert len(output) > 0  # Should say something about the problem
```

### Test 4: Snapshot and Import Roundtrip

```python
def test_snapshot_import_roundtrip(tmp_path):
    """Snapshot expertise, import into new project, verify modules survive."""
    project_a = tmp_path / "project_a"
    project_a.mkdir()
    run_stato(["init"], cwd=project_a)
    
    # Create a skill
    skill_path = project_a / ".stato" / "skills" / "qc.py"
    skill_path.write_text('''
class QualityControl:
    name = "qc_filtering"
    version = "1.0.0"
    depends_on = ["scanpy"]
    default_params = {"max_pct_mito": 20}
    lessons_learned = "FFPE needs 40"
    @staticmethod
    def run(**kwargs): pass
''')
    
    # Snapshot
    run_stato(["snapshot", "--name", "test-export", "--force"], cwd=project_a)
    archive = project_a / "test-export.stato"
    assert archive.exists(), "Snapshot archive not created"
    
    # Import into new project
    project_b = tmp_path / "project_b"
    project_b.mkdir()
    run_stato(["init"], cwd=project_b)
    run_stato(["import", str(archive)], cwd=project_b)
    
    # Verify skill survived
    imported_skill = project_b / ".stato" / "skills" / "qc.py"
    assert imported_skill.exists(), "Skill not imported"
    content = imported_skill.read_text()
    assert "qc_filtering" in content
    assert "max_pct_mito" in content


def test_snapshot_template_resets_progress(tmp_path):
    """Template mode preserves skills but resets plan progress."""
    run_stato(["init"], cwd=tmp_path)
    
    # Create skill + plan
    (tmp_path / ".stato" / "skills" / "qc.py").write_text('''
class QualityControl:
    name = "qc_filtering"
    version = "1.0.0"
    depends_on = []
    default_params = {"max_pct_mito": 20}
    lessons_learned = "Test"
    @staticmethod
    def run(**kwargs): pass
''')
    
    (tmp_path / ".stato" / "plan.py").write_text('''
class AnalysisPlan:
    project = "test"
    steps = [
        {"id": 1, "name": "load", "status": "complete"},
        {"id": 2, "name": "analyze", "status": "pending"},
    ]
    current_step = 2
    decision_log = ["Test decision"]
''')
    
    # Snapshot with template
    run_stato(["snapshot", "--name", "template-test", "--template", "--force"], cwd=tmp_path)
    archive = tmp_path / "template-test.stato"
    assert archive.exists()
    
    # Import into new project
    new_project = tmp_path / "new"
    new_project.mkdir()
    run_stato(["init"], cwd=new_project)
    run_stato(["import", str(archive)], cwd=new_project)
    
    # Skill should exist
    assert (new_project / ".stato" / "skills" / "qc.py").exists()
    
    # Plan should have progress reset (if template mode resets step status)
    plan_content = (new_project / ".stato" / "plan.py").read_text()
    # Template should reset completed steps to pending
    # (verify based on actual template behavior)
```

### Test 5: Bridge Generation All Platforms

```python
def test_bridge_all_platforms(tmp_path):
    """Generate bridges for all 4 platforms, verify content."""
    run_stato(["init"], cwd=tmp_path)
    
    # Create two skills
    for name, cls in [("qc", "QualityControl"), ("norm", "Normalization")]:
        (tmp_path / ".stato" / "skills" / f"{name}.py").write_text(f'''
class {cls}:
    name = "{name}"
    version = "1.0.0"
    depends_on = ["scanpy"]
    default_params = {{"{name}_param": 1}}
    lessons_learned = "Lesson for {name}"
    @staticmethod
    def run(**kwargs): pass
''')
    
    # Generate all bridges
    run_stato(["bridge", "--platform", "all"], cwd=tmp_path)
    
    bridges = {
        "CLAUDE.md": tmp_path / "CLAUDE.md",
        ".cursorrules": tmp_path / ".cursorrules",
        "AGENTS.md": tmp_path / "AGENTS.md",
        "README.stato.md": tmp_path / "README.stato.md",
    }
    
    for name, path in bridges.items():
        assert path.exists(), f"{name} not generated"
        content = path.read_text()
        # Each bridge should reference both skills
        assert "qc" in content.lower(), f"{name} missing qc reference"
        assert "norm" in content.lower(), f"{name} missing norm reference"
        # Each bridge should reference .stato/ paths
        assert ".stato/" in content, f"{name} missing .stato/ path references"


def test_bridge_token_budget(tmp_path):
    """Bridge files should be compact indexes, not full dumps."""
    run_stato(["init"], cwd=tmp_path)
    
    # Create 10 skills
    for i in range(10):
        (tmp_path / ".stato" / "skills" / f"skill_{i}.py").write_text(f'''
class Skill{i}:
    name = "skill_{i}"
    version = "1.0.0"
    depends_on = []
    default_params = {{"param": {i}}}
    lessons_learned = "Lesson {i} with some detail about what was learned"
    @staticmethod
    def run(**kwargs): pass
''')
    
    run_stato(["bridge", "--platform", "claude"], cwd=tmp_path)
    
    claude_md = (tmp_path / "CLAUDE.md").read_text()
    word_count = len(claude_md.split())
    
    # 10 skills should still produce a bridge under 1500 words
    assert word_count < 1500, (
        f"CLAUDE.md is {word_count} words for 10 skills. "
        f"Bridge should be a compact index, not a full dump."
    )
```

### Test 6: Bundle Import

```python
VALID_BUNDLE = '''
SKILLS = {
    "data_loading": \'\'\'
class DataLoading:
    name = "data_loading"
    version = "1.0.0"
    depends_on = ["pandas"]
    default_params = {"chunk_size": 10000}
    lessons_learned = "Use chunked reading for large files"
    @staticmethod
    def run(**kwargs): pass
\\\'\\\'\\\',
    "preprocessing": \\\'\\\'\\\'
class Preprocessing:
    name = "preprocessing"
    version = "1.0.0"
    depends_on = ["pandas", "numpy"]
    default_params = {"fill_method": "median"}
    lessons_learned = "Median fill is more robust than mean"
    @staticmethod
    def run(**kwargs): pass
\\\'\\\'\\\',
}

PLAN = \\\'\\\'\\\'
class AnalysisPlan:
    project = "test_pipeline"
    steps = [{"id": 1, "name": "load", "status": "complete"}]
    current_step = 1
    decision_log = ["Test"]
\\\'\\\'\\\'

MEMORY = \\\'\\\'\\\'
class ProjectState:
    phase = "development"
    known_issues = ["Test issue"]
    reflection = "Test reflection"
\\\'\\\'\\\'

CONTEXT = \\\'\\\'\\\'
class PipelineContext:
    project = "test_pipeline"
    description = "Test pipeline"
    environment = {"python": "3.12"}
    conventions = ["Type hints required"]
\\\'\\\'\\\'
'''
# NOTE: The bundle above uses escaped quotes for the prompt.
# In the actual test, write the bundle with proper triple-quote 
# formatting. Build the bundle string programmatically or use
# a fixture file.


def test_bundle_import(tmp_path):
    """Import a stato bundle file and verify all modules land."""
    run_stato(["init"], cwd=tmp_path)
    
    # Write a bundle file (build it carefully to avoid quote issues)
    bundle_path = tmp_path / "stato_bundle.py"
    bundle_content = _build_test_bundle()
    bundle_path.write_text(bundle_content)
    
    # Import
    result = run_stato(["import-bundle", str(bundle_path)], cwd=tmp_path)
    
    # Verify modules exist
    skills_dir = tmp_path / ".stato" / "skills"
    assert any(skills_dir.iterdir()), "No skills imported from bundle"
    
    # Status should show imported modules
    result = run_stato(["status"], cwd=tmp_path)
    assert len(result.stdout) > 0


def _build_test_bundle() -> str:
    """Build a valid stato bundle file for testing."""
    return '''# stato_bundle.py
SKILLS = {
    "data_loading": \'\'\'class DataLoading:
    name = "data_loading"
    version = "1.0.0"
    depends_on = ["pandas"]
    default_params = {"chunk_size": 10000}
    lessons_learned = "Use chunked reading for large files"
    @staticmethod
    def run(**kwargs): pass
\'\'\',
}

PLAN = \'\'\'class TestPlan:
    project = "test"
    steps = [{"id": 1, "name": "load", "status": "complete"}]
    current_step = 1
    decision_log = ["Started"]
\'\'\'

MEMORY = \'\'\'class TestMemory:
    phase = "dev"
    known_issues = ["None"]
    reflection = "Going well"
\'\'\'

CONTEXT = \'\'\'class TestContext:
    project = "test"
    description = "Test project"
    environment = {"python": "3.12"}
    conventions = ["Use type hints"]
\'\'\'
'''
```

**IMPORTANT:** The bundle formatting with triple quotes is tricky. Build the test bundle carefully. Write the `_build_test_bundle()` function so it produces valid Python that the bundle parser can parse. Test it manually first:

```python
# Quick validation that the bundle is parseable
content = _build_test_bundle()
import ast
ast.parse(content)  # Should not raise
```

### Test 7: Convert

```python
def test_convert_claude_md(tmp_path):
    """Convert a CLAUDE.md file to stato modules."""
    run_stato(["init"], cwd=tmp_path)
    
    claude_md = tmp_path / "test_claude.md"
    claude_md.write_text("""# My Project
Python 3.12, always use type hints.

## Database
Use SQLAlchemy 2.0.
pool_size=10
Always use alembic for migrations.

## API
Use FastAPI with Pydantic v2.
Return 422 for validation errors.
""")
    
    result = run_stato(["convert", str(claude_md)], cwd=tmp_path)
    # Should report extracted modules
    output = result.stdout
    assert "skills" in output.lower() or "context" in output.lower() or "module" in output.lower()


def test_convert_cursorrules(tmp_path):
    """Convert a .cursorrules file."""
    run_stato(["init"], cwd=tmp_path)
    
    cursorrules = tmp_path / ".cursorrules"
    cursorrules.write_text("Always use TypeScript\nPrefer functional components\nUse Tailwind")
    
    result = run_stato(["convert", str(cursorrules), "--format", "cursor"], cwd=tmp_path)
    assert result.returncode == 0


def test_convert_skillkit(tmp_path):
    """Convert a SKILL.md file."""
    run_stato(["init"], cwd=tmp_path)
    
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("""# Data Validation

## Steps
1. Check file exists
2. Validate headers

## Rules
- Always validate before processing
- Log failures with line numbers
""")
    
    result = run_stato(["convert", str(skill_md)], cwd=tmp_path)
    assert result.returncode == 0


def test_convert_dry_run(tmp_path):
    """Dry run should show plan without writing files."""
    run_stato(["init"], cwd=tmp_path)
    
    md_file = tmp_path / "test.md"
    md_file.write_text("# Test\n## Section\nAlways do X\nparam=42")
    
    skills_before = list((tmp_path / ".stato" / "skills").iterdir())
    
    result = run_stato(["convert", str(md_file), "--dry-run"], cwd=tmp_path)
    
    skills_after = list((tmp_path / ".stato" / "skills").iterdir())
    assert len(skills_before) == len(skills_after), "Dry run should not write files"
```

### Test 8: Merge

```python
def _create_archive_with_skill(project_dir: Path, skill_name: str, 
                                skill_content: str, archive_name: str) -> Path:
    """Helper: init project, write skill, snapshot, return archive path."""
    project_dir.mkdir(exist_ok=True)
    run_stato(["init"], cwd=project_dir)
    (project_dir / ".stato" / "skills" / f"{skill_name}.py").write_text(skill_content)
    run_stato(["snapshot", "--name", archive_name, "--force"], cwd=project_dir)
    return project_dir / f"{archive_name}.stato"


def test_merge_union(tmp_path):
    """Merge two archives with union strategy."""
    archive_a = _create_archive_with_skill(
        tmp_path / "a", "qc", '''
class QC:
    name = "qc"
    version = "1.0.0"
    depends_on = ["scanpy"]
    default_params = {"max_pct_mito": 20}
    lessons_learned = "Standard threshold"
    @staticmethod
    def run(**kwargs): pass
''', "archive-a")
    
    archive_b = _create_archive_with_skill(
        tmp_path / "b", "clustering", '''
class Clustering:
    name = "clustering"
    version = "1.0.0"
    depends_on = ["scanpy"]
    default_params = {"resolution": 0.6}
    lessons_learned = "Leiden at 0.6"
    @staticmethod
    def run(**kwargs): pass
''', "archive-b")
    
    output = tmp_path / "merged.stato"
    result = run_stato(["merge", str(archive_a), str(archive_b), 
                        "-o", str(output)], cwd=tmp_path)
    assert output.exists(), "Merged archive not created"


def test_merge_conflict_detection(tmp_path):
    """Merge detects conflicting parameter values."""
    skill_a = '''
class QC:
    name = "qc"
    version = "1.0.0"
    depends_on = ["scanpy"]
    default_params = {"max_pct_mito": 20}
    lessons_learned = "Fresh tissue"
    @staticmethod
    def run(**kwargs): pass
'''
    skill_b = '''
class QC:
    name = "qc"
    version = "1.1.0"
    depends_on = ["scanpy"]
    default_params = {"max_pct_mito": 40}
    lessons_learned = "FFPE tissue"
    @staticmethod
    def run(**kwargs): pass
'''
    archive_a = _create_archive_with_skill(tmp_path / "a", "qc", skill_a, "a")
    archive_b = _create_archive_with_skill(tmp_path / "b", "qc", skill_b, "b")
    
    output = tmp_path / "merged.stato"
    result = run_stato(["merge", str(archive_a), str(archive_b),
                        "-o", str(output)], cwd=tmp_path)
    
    # Should mention conflict in output
    combined = result.stdout + result.stderr
    assert "conflict" in combined.lower() or "max_pct_mito" in combined


def test_merge_dry_run(tmp_path):
    """Dry run shows merge plan without creating output."""
    archive_a = _create_archive_with_skill(
        tmp_path / "a", "qc", '''
class QC:
    name = "qc"
    version = "1.0.0"
    depends_on = []
    default_params = {}
    lessons_learned = "Test"
    @staticmethod
    def run(**kwargs): pass
''', "a")
    
    archive_b = _create_archive_with_skill(tmp_path / "b", "qc", '''
class QC:
    name = "qc"
    version = "1.0.0"
    depends_on = []
    default_params = {}
    lessons_learned = "Test"
    @staticmethod
    def run(**kwargs): pass
''', "b")
    
    output = tmp_path / "merged.stato"
    result = run_stato(["merge", str(archive_a), str(archive_b),
                        "-o", str(output), "--dry-run"], cwd=tmp_path)
    assert not output.exists(), "Dry run should not create output file"
```

### Test 9: Registry Index Valid

```python
def test_registry_index_valid_toml():
    """The seed registry index.toml is valid TOML with expected structure."""
    import tomli
    
    # Find the registry index relative to the repo root
    # Adjust path based on actual repo structure
    repo_root = Path(__file__).parent.parent
    index_path = repo_root / "docs" / "registry" / "index.toml"
    
    if not index_path.exists():
        pytest.skip("Registry index not found at expected path")
    
    with open(index_path, "rb") as f:
        data = tomli.load(f)
    
    assert "meta" in data, "Missing [meta] section"
    assert "packages" in data, "Missing [packages] section"
    assert len(data["packages"]) >= 1, "Registry should have at least one seed package"
    
    for name, pkg in data["packages"].items():
        assert "description" in pkg, f"Package {name} missing description"
        assert "author" in pkg, f"Package {name} missing author"
        assert "version" in pkg, f"Package {name} missing version"
        assert "url" in pkg, f"Package {name} missing url"


def test_registry_commands_dont_crash():
    """Registry commands produce clean output or clean errors (no tracebacks)."""
    # list (may fail with network error, that's OK)
    result = subprocess.run(
        ["stato", "registry", "list"],
        capture_output=True, text=True
    )
    assert "Traceback" not in result.stderr, "Registry list produced a traceback"
    
    # search
    result = subprocess.run(
        ["stato", "registry", "search", "test"],
        capture_output=True, text=True
    )
    assert "Traceback" not in result.stderr, "Registry search produced a traceback"
```

### Test 10: Diff

```python
def test_diff_shows_changes(tmp_path):
    """Diff command shows field-level differences."""
    run_stato(["init"], cwd=tmp_path)
    
    skill_path = tmp_path / ".stato" / "skills" / "qc.py"
    skill_path.write_text('''
class QC:
    name = "qc"
    version = "1.0.0"
    depends_on = ["scanpy"]
    default_params = {"max_pct_mito": 20}
    lessons_learned = "Standard"
    @staticmethod
    def run(**kwargs): pass
''')
    
    # Run diff (behavior depends on implementation: may diff against
    # last validated version, or require two paths)
    result = run_stato(["diff", ".stato/skills/qc.py"], cwd=tmp_path, expect_fail=True)
    # Should not traceback regardless of whether diff has something to compare
    combined = result.stdout + result.stderr
    assert "Traceback" not in combined
```

### Test 11: Resume

```python
def test_resume_all_formats(tmp_path):
    """Resume produces output in all three formats."""
    run_stato(["init"], cwd=tmp_path)
    
    # Create modules for resume to read
    (tmp_path / ".stato" / "skills" / "qc.py").write_text('''
class QC:
    name = "qc"
    version = "1.0.0"
    depends_on = ["scanpy"]
    default_params = {"max_pct_mito": 20}
    lessons_learned = "FFPE needs 40"
    @staticmethod
    def run(**kwargs): pass
''')
    
    (tmp_path / ".stato" / "plan.py").write_text('''
class Plan:
    project = "cortex"
    steps = [
        {"id": 1, "name": "load", "status": "complete"},
        {"id": 2, "name": "qc", "status": "pending"},
    ]
    current_step = 2
    decision_log = ["Using scanpy"]
''')
    
    (tmp_path / ".stato" / "memory.py").write_text('''
class Memory:
    phase = "analysis"
    known_issues = ["Plate 2 batch effects"]
    reflection = "QC working well"
''')
    
    # Default format
    result = run_stato(["resume"], cwd=tmp_path)
    assert len(result.stdout) > 50, "Resume output too short"
    assert "cortex" in result.stdout.lower() or "qc" in result.stdout.lower()
    
    # Brief format
    result = run_stato(["resume", "--brief"], cwd=tmp_path)
    assert len(result.stdout) > 20
    
    # Raw format
    result = run_stato(["resume", "--raw"], cwd=tmp_path)
    assert len(result.stdout) > 20
```

### Test 12: Error Handling (No Tracebacks)

This is the most important integration test. Users will make mistakes.

```python
def test_no_traceback_on_missing_stato_dir(tmp_path):
    """Commands in a directory without .stato/ give clean errors."""
    commands = [
        ["status"],
        ["validate", ".stato/"],
        ["bridge", "--platform", "claude"],
        ["resume"],
    ]
    for cmd in commands:
        result = subprocess.run(
            ["stato"] + cmd,
            capture_output=True, text=True,
            cwd=str(tmp_path),
        )
        combined = result.stdout + result.stderr
        assert "Traceback" not in combined, (
            f"stato {' '.join(cmd)} produced a traceback:\n{combined}"
        )


def test_no_traceback_on_missing_files(tmp_path):
    """Commands with nonexistent file paths give clean errors."""
    test_cases = [
        ["convert", str(tmp_path / "nonexistent.md")],
        ["import-bundle", str(tmp_path / "nonexistent.py")],
        ["merge", str(tmp_path / "a.stato"), str(tmp_path / "b.stato")],
        ["import", str(tmp_path / "nonexistent.stato")],
    ]
    for cmd in test_cases:
        result = subprocess.run(
            ["stato"] + cmd,
            capture_output=True, text=True,
            cwd=str(tmp_path),
        )
        combined = result.stdout + result.stderr
        assert "Traceback" not in combined, (
            f"stato {' '.join(cmd)} produced a traceback:\n{combined}"
        )


def test_no_traceback_on_bad_bundle(tmp_path):
    """Importing a malformed bundle gives clean error."""
    run_stato(["init"], cwd=tmp_path)
    
    bad_bundle = tmp_path / "bad.py"
    bad_bundle.write_text("this is not valid python at all {{{")
    
    result = subprocess.run(
        ["stato", "import-bundle", str(bad_bundle)],
        capture_output=True, text=True,
        cwd=str(tmp_path),
    )
    combined = result.stdout + result.stderr
    assert "Traceback" not in combined


def test_no_traceback_on_empty_bundle(tmp_path):
    """Importing an empty file gives clean error."""
    run_stato(["init"], cwd=tmp_path)
    
    empty = tmp_path / "empty.py"
    empty.write_text("")
    
    result = subprocess.run(
        ["stato", "import-bundle", str(empty)],
        capture_output=True, text=True,
        cwd=str(tmp_path),
    )
    combined = result.stdout + result.stderr
    assert "Traceback" not in combined
```

### Test 13: Repo Hygiene

```python
def test_no_secrets_in_source():
    """No API keys or tokens in source files (except test fixtures)."""
    import re
    
    repo_root = Path(__file__).parent.parent
    src_dir = repo_root / "src"
    
    if not src_dir.exists():
        pytest.skip("src/ not found")
    
    secret_patterns = [
        r'sk-[a-zA-Z0-9]{20,}',        # OpenAI-style keys
        r'ghp_[a-zA-Z0-9]{20,}',        # GitHub tokens
        r'AKIA[A-Z0-9]{16}',            # AWS access keys
    ]
    
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text()
        for pattern in secret_patterns:
            matches = re.findall(pattern, content)
            assert not matches, (
                f"Possible secret found in {py_file}: {matches[0][:10]}..."
            )


def test_no_stale_name_references():
    """No references to old 'agentstate' name in source or docs."""
    repo_root = Path(__file__).parent.parent
    
    for pattern_dir in ["src", "docs"]:
        search_dir = repo_root / pattern_dir
        if not search_dir.exists():
            continue
        for f in search_dir.rglob("*"):
            if f.is_file() and f.suffix in (".py", ".md", ".mdx", ".toml"):
                content = f.read_text()
                assert "agentstate" not in content.lower(), (
                    f"Stale 'agentstate' reference in {f}"
                )


def test_readme_commands_exist():
    """Every 'stato <cmd>' in README.md corresponds to a real command."""
    import re
    
    repo_root = Path(__file__).parent.parent
    readme = repo_root / "README.md"
    
    if not readme.exists():
        pytest.skip("README.md not found")
    
    content = readme.read_text()
    
    # Extract unique commands like "stato init", "stato bridge", etc.
    commands = set(re.findall(r'stato\s+(\w+)', content))
    
    # These are subcommands or flags, not top-level commands
    skip = {"install", "self", "dev", "the", "is", "and", "for", "a"}
    commands -= skip
    
    for cmd in commands:
        result = subprocess.run(
            ["stato", cmd, "--help"],
            capture_output=True, text=True,
        )
        # Allow failure for subcommands like "registry search"
        # but should never produce "No such command" without explanation
        combined = result.stdout + result.stderr
        assert "Traceback" not in combined, (
            f"stato {cmd} --help produced traceback"
        )
```

### Test 14: pyproject.toml

```python
def test_pyproject_has_required_fields():
    """pyproject.toml has all fields needed for PyPI publication."""
    import tomli
    
    repo_root = Path(__file__).parent.parent
    pyproject = repo_root / "pyproject.toml"
    
    assert pyproject.exists(), "pyproject.toml not found"
    
    with open(pyproject, "rb") as f:
        data = tomli.load(f)
    
    project = data.get("project", {})
    
    assert project.get("name"), "Missing project name"
    assert project.get("version"), "Missing project version"
    assert project.get("description"), "Missing project description"
    assert project.get("license"), "Missing project license"
    assert project.get("requires-python"), "Missing requires-python"
    assert project.get("authors"), "Missing authors"
    assert project.get("dependencies") is not None, "Missing dependencies"
    
    # Entry point
    scripts = project.get("scripts", {})
    assert "stato" in scripts, "Missing 'stato' entry point in [project.scripts]"
    
    # URLs
    urls = project.get("urls", {})
    assert urls.get("Repository") or urls.get("Homepage"), "Missing project URL"
    
    # Build system
    build = data.get("build-system", {})
    assert build.get("build-backend"), "Missing build-backend"


def test_package_builds():
    """The package builds without errors."""
    repo_root = Path(__file__).parent.parent
    
    result = subprocess.run(
        ["python", "-m", "build", "--sdist", "--no-isolation"],
        capture_output=True, text=True,
        cwd=str(repo_root),
    )
    assert result.returncode == 0, (
        f"Package build failed:\n{result.stderr}"
    )
```

---

## After All Tests Pass

Run the complete suite:

```bash
# Unit tests only (fast)
pytest tests/ -m "not agent and not integration" -v

# Integration tests only
pytest tests/test_integration.py -v

# Everything
pytest tests/ -m "not agent" -v
```

Report:
1. Total test count (unit + integration)
2. Any failures with details
3. Fix all failures before completing