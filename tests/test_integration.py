"""Integration tests -- subprocess-based CLI smoke tests.

Every test runs `stato` as a subprocess and asserts:
  1. Expected return code (0 for success, 1 for expected failures)
  2. No Python tracebacks in stderr
  3. Key output strings in stdout
"""
import subprocess
from pathlib import Path

import pytest

from stato.core.state_manager import init_project, write_module
from tests.fixtures import (
    VALID_QC_SKILL,
    VALID_NORMALIZE_SKILL,
    VALID_PLAN,
    VALID_MEMORY,
    VALID_CONTEXT,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run_stato(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a stato CLI command and assert no tracebacks."""
    result = subprocess.run(
        ["stato", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    assert "Traceback" not in result.stderr, (
        f"stato {' '.join(args)} produced a traceback:\n{result.stderr}"
    )
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_init(tmp_path):
    """stato init creates .stato/ directory."""
    r = run_stato("init", "--path", str(tmp_path))
    assert r.returncode == 0
    assert (tmp_path / ".stato").is_dir()
    assert "Initialized" in r.stdout


def test_validate_valid(tmp_path):
    """stato validate on a valid module passes."""
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", VALID_QC_SKILL)

    r = run_stato("validate", str(tmp_path / ".stato"))
    assert r.returncode == 0
    assert "valid" in r.stdout.lower()


def test_validate_invalid(tmp_path):
    """stato validate on an invalid module exits 1 without traceback."""
    init_project(tmp_path)
    bad_file = tmp_path / ".stato" / "skills" / "bad.py"
    bad_file.parent.mkdir(parents=True, exist_ok=True)
    bad_file.write_text("class Bad:\n    pass  # missing name, missing run()\n")

    r = run_stato("validate", str(bad_file))
    assert r.returncode == 1


def test_status(tmp_path):
    """stato status shows module table."""
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", VALID_QC_SKILL)

    r = run_stato("status", "--path", str(tmp_path))
    assert r.returncode == 0
    assert "qc" in r.stdout.lower()


def test_crystallize(tmp_path):
    """stato crystallize --print prints prompt text."""
    r = run_stato("crystallize", "--print", "--path", str(tmp_path))
    assert r.returncode == 0
    assert len(r.stdout) > 100
    assert "stato" in r.stdout.lower()


def test_crystallize_web(tmp_path):
    """stato crystallize --web prints web bundle instructions."""
    r = run_stato("crystallize", "--web", "--path", str(tmp_path))
    assert r.returncode == 0
    assert "SKILLS" in r.stdout


def test_snapshot_and_inspect(tmp_path):
    """stato snapshot creates archive; stato inspect shows contents."""
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", VALID_QC_SKILL)

    archive = tmp_path / "test.stato"
    r = run_stato(
        "snapshot", "--name", "test",
        "--force", "--output", str(archive),
        "--path", str(tmp_path),
    )
    assert r.returncode == 0
    assert archive.exists()

    r2 = run_stato("inspect", str(archive))
    assert r2.returncode == 0
    assert "qc" in r2.stdout.lower()


def test_import(tmp_path):
    """stato import brings modules from archive into new project."""
    # Source project
    src = tmp_path / "src_project"
    src.mkdir()
    init_project(src)
    write_module(src, "skills/qc.py", VALID_QC_SKILL)

    archive = tmp_path / "export.stato"
    run_stato(
        "snapshot", "--name", "export",
        "--force", "--output", str(archive),
        "--path", str(src),
    )

    # Target project
    dst = tmp_path / "dst_project"
    dst.mkdir()
    init_project(dst)

    r = run_stato("import", str(archive), "--path", str(dst))
    assert r.returncode == 0
    assert (dst / ".stato" / "skills" / "qc.py").exists()


def test_slice(tmp_path):
    """stato slice extracts a module into a slice archive."""
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", VALID_QC_SKILL)

    out = tmp_path / "sliced.stato"
    r = run_stato(
        "slice", "--module", "skills/qc.py",
        "--output", str(out),
        "--path", str(tmp_path),
    )
    assert r.returncode == 0
    assert out.exists()


def test_bridge(tmp_path):
    """stato bridge generates CLAUDE.md."""
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", VALID_QC_SKILL)

    r = run_stato("bridge", "--platform", "claude", "--path", str(tmp_path))
    assert r.returncode == 0
    assert (tmp_path / "CLAUDE.md").exists()


def test_diff_no_backup(tmp_path):
    """stato diff with no backup returns gracefully."""
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", VALID_QC_SKILL)

    r = run_stato("diff", "skills/qc.py", "--path", str(tmp_path))
    assert r.returncode == 0
    assert "backup" in r.stdout.lower() or "No" in r.stdout


def test_resume(tmp_path):
    """stato resume --raw outputs project recap."""
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", VALID_QC_SKILL)
    write_module(tmp_path, "plan.py", VALID_PLAN)
    write_module(tmp_path, "context.py", VALID_CONTEXT)

    r = run_stato("resume", "--raw", "--path", str(tmp_path))
    assert r.returncode == 0
    assert "cortex" in r.stdout.lower()


def test_convert_dry_run(tmp_path):
    """stato convert --dry-run parses without writing."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "# My Project\n\n"
        "## Rules\n\n"
        "- Always use pytest for testing\n"
        "- Format with black\n\n"
        "## Environment\n\n"
        "- Python 3.11\n"
        "- Ubuntu 22.04\n"
    )

    r = run_stato("convert", str(claude_md), "--dry-run")
    assert r.returncode == 0
    assert "dry run" in r.stdout.lower() or "Dry run" in r.stdout


def test_merge_dry_run(tmp_path):
    """stato merge --dry-run shows merge plan without writing."""
    # Create two archives with different skills
    proj_a = tmp_path / "proj_a"
    proj_a.mkdir()
    init_project(proj_a)
    write_module(proj_a, "skills/qc.py", VALID_QC_SKILL)
    archive_a = tmp_path / "a.stato"
    run_stato(
        "snapshot", "--name", "a",
        "--force", "--output", str(archive_a),
        "--path", str(proj_a),
    )

    proj_b = tmp_path / "proj_b"
    proj_b.mkdir()
    init_project(proj_b)
    write_module(proj_b, "skills/normalize.py", VALID_NORMALIZE_SKILL)
    archive_b = tmp_path / "b.stato"
    run_stato(
        "snapshot", "--name", "b",
        "--force", "--output", str(archive_b),
        "--path", str(proj_b),
    )

    r = run_stato("merge", str(archive_a), str(archive_b), "--dry-run")
    assert r.returncode == 0
    assert "dry run" in r.stdout.lower() or "Dry run" in r.stdout
    assert "modules" in r.stdout.lower() or "Total" in r.stdout
