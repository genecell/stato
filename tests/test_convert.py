"""Tests for the convert command — importing from CLAUDE.md, .cursorrules, etc."""
from stato.core.converter import (
    detect_format,
    convert_file,
    ConvertResult,
    SourceFormat,
)
from stato.core.state_manager import init_project, write_module


def test_detect_claude_md(tmp_path):
    f = tmp_path / "CLAUDE.md"
    f.write_text("# My Project\n## Database\nUse PostgreSQL")
    assert detect_format(f) == SourceFormat.CLAUDE


def test_detect_cursorrules(tmp_path):
    f = tmp_path / ".cursorrules"
    f.write_text("Always use TypeScript\nPrefer functional components")
    assert detect_format(f) == SourceFormat.CURSOR


def test_detect_agents_md(tmp_path):
    f = tmp_path / "AGENTS.md"
    f.write_text("# Agent Instructions\nUse pytest")
    assert detect_format(f) == SourceFormat.CODEX


def test_detect_skill_md(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("# Data Loading\n## Steps\n1. Read CSV\n## Rules\n- Validate headers")
    assert detect_format(f) == SourceFormat.SKILLKIT


def test_detect_generic(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("Some random notes about the project")
    assert detect_format(f) == SourceFormat.GENERIC


def test_convert_claude_md_extracts_skills(tmp_path):
    f = tmp_path / "CLAUDE.md"
    f.write_text("""# My Project
Python 3.12, always use type hints.

## Database
Use SQLAlchemy 2.0 async.
pool_size=10
Always use alembic for migrations.

## API
Use FastAPI with Pydantic v2.
Return 422 for validation errors.
""")
    result = convert_file(f)
    assert result.source_format == SourceFormat.CLAUDE
    assert len(result.skills) >= 1
    assert result.context is not None


def test_convert_claude_md_extracts_environment(tmp_path):
    f = tmp_path / "CLAUDE.md"
    f.write_text("# Project\nPython 3.12\nNode 18\n## Rules\nAlways test")
    result = convert_file(f)
    assert result.context is not None
    assert "3.12" in result.context


def test_convert_cursorrules_plain(tmp_path):
    f = tmp_path / ".cursorrules"
    f.write_text("Always use TypeScript\nPrefer functional components\nUse Tailwind for styling")
    result = convert_file(f)
    assert result.context is not None
    assert "TypeScript" in result.context


def test_convert_skillkit(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("""# Data Validation
Validates input data files before processing.

## Steps
1. Check file exists
2. Validate headers match schema
3. Check for missing values
4. Verify data types

## Rules
- Always validate before processing
- Log validation failures with line numbers
- Skip rows with > 50% missing values
""")
    result = convert_file(f)
    assert len(result.skills) == 1
    assert "data_validation" in result.skills
    skill_source = result.skills["data_validation"]
    assert "validate" in skill_source.lower()


def test_convert_empty_file(tmp_path):
    f = tmp_path / "empty.md"
    f.write_text("")
    result = convert_file(f)
    assert isinstance(result, ConvertResult)


def test_convert_extract_params(tmp_path):
    f = tmp_path / "CLAUDE.md"
    f.write_text("""# Test
## Config
batch_size=32
learning_rate=0.001
use_gpu=True
""")
    result = convert_file(f)
    assert len(result.skills) >= 1 or result.context is not None


def test_convert_write_modules(tmp_path):
    """Full roundtrip: convert -> write -> validate."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("""# My Project
Python 3.12

## Database
Use SQLAlchemy 2.0.
pool_size=10
Always use alembic for migrations.
""")

    project = tmp_path / "project"
    project.mkdir()
    init_project(project)

    result = convert_file(claude_md)

    if result.context:
        wr = write_module(project, "context.py", result.context)
        assert wr.success

    for name, source in result.skills.items():
        wr = write_module(project, f"skills/{name}.py", source)
        assert wr.success
