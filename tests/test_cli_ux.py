"""Tests for CLI UX: --json, --quiet, --dry-run, find, hints (WS7)."""
import json

from click.testing import CliRunner

from stato.cli import main
from stato.core.state_manager import init_project, write_module
from tests.fixtures import VALID_MEMORY, VALID_PLAN, VALID_QC_SKILL


def _project(tmp_path):
    project = init_project(tmp_path)
    write_module(project, "skills/qc.py", VALID_QC_SKILL)
    write_module(project, "plan.py", VALID_PLAN)
    write_module(project, "memory.py", VALID_MEMORY)
    return project


def test_status_json(tmp_path):
    _project(tmp_path)
    result = CliRunner().invoke(main, ["status", "--json", "--path", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert {m["path"] for m in payload["modules"]} >= {"plan.py", "memory.py", "skills/qc.py"}
    assert payload["plans"][0]["total"] > 0


def test_validate_json(tmp_path):
    _project(tmp_path)
    result = CliRunner().invoke(
        main, ["validate", str(tmp_path / ".stato"), "--json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["total_errors"] == 0
    assert all(f["success"] for f in payload["files"])


def test_resume_json(tmp_path):
    _project(tmp_path)
    result = CliRunner().invoke(main, ["resume", "--json", "--path", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "text" in payload and payload["text"]


def test_inspect_json(tmp_path):
    _project(tmp_path)
    result = CliRunner().invoke(
        main, ["snapshot", "--name", "t", "--force", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    result = CliRunner().invoke(main, ["inspect", str(tmp_path / "t.stato"), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["format_version"] == "1"
    assert payload["integrity"]["ok"] is True


def test_find_json(tmp_path):
    _project(tmp_path)
    result = CliRunner().invoke(
        main, ["find", "qc filtering", "--json", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["results"], "expected qc skill to match"
    assert payload["results"][0]["path"] == "skills/qc.py"


def test_quiet_suppresses_output(tmp_path):
    _project(tmp_path)
    result = CliRunner().invoke(main, ["-q", "status", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_quiet_json_still_prints(tmp_path):
    _project(tmp_path)
    result = CliRunner().invoke(
        main, ["-q", "status", "--json", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert json.loads(result.output)


def test_snapshot_dry_run_writes_nothing(tmp_path):
    _project(tmp_path)
    result = CliRunner().invoke(
        main, ["snapshot", "--name", "t", "--dry-run", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert not (tmp_path / "t.stato").exists()


def test_slice_dry_run_writes_nothing(tmp_path):
    _project(tmp_path)
    result = CliRunner().invoke(
        main,
        ["slice", "--module", "skills/qc", "--dry-run", "--path", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert not list(tmp_path.glob("*.stato")) or not any(
        p.is_file() for p in tmp_path.glob("*.stato")
    )


def test_graft_dry_run_writes_nothing(tmp_path):
    _project(tmp_path / "src")
    CliRunner().invoke(
        main, ["snapshot", "--name", "t", "--force", "--path", str(tmp_path / "src")]
    )
    dest = tmp_path / "dest"
    dest.mkdir()
    init_project(dest)
    result = CliRunner().invoke(
        main,
        ["graft", str(tmp_path / "src" / "t.stato"), "--dry-run",
         "--on-conflict", "replace", "--path", str(dest)],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert not (dest / ".stato" / "skills" / "qc.py").exists()


def test_error_hint_shown(tmp_path):
    init_project(tmp_path)
    bad = tmp_path / "bad.py"
    bad.write_text('''
class P:
    """Plan with a cycle."""
    name = "p"
    objective = "x"
    steps = [
        {"id": 1, "action": "a", "status": "pending", "depends_on": [2]},
        {"id": 2, "action": "b", "status": "pending", "depends_on": [1]},
    ]
''')
    result = CliRunner().invoke(main, ["validate", str(bad)])
    assert result.exit_code == 1
    assert "hint:" in result.output
    assert "loop" in result.output


def test_registry_package_entry(tmp_path):
    _project(tmp_path)
    CliRunner().invoke(
        main, ["snapshot", "--name", "pkg", "--force", "--path", str(tmp_path)]
    )
    result = CliRunner().invoke(
        main,
        ["registry", "package", str(tmp_path / "pkg.stato"),
         "--url", "https://x/pkg.stato", "--author", "tester"],
    )
    assert result.exit_code == 0
    assert "[packages.pkg]" in result.output
    assert "sha256:" in result.output
