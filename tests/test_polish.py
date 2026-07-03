"""Tests for the 0.8.1 polish: version header/mismatch, doctor, auto-stamp."""
import json

from click.testing import CliRunner

from stato import __version__
from stato.cli import main
from stato.core.resume import generate_resume
from stato.core.state_manager import StateManager, init_project, write_module
from tests.fixtures import VALID_MEMORY, VALID_PLAN, VALID_QC_SKILL

CTX_STALE = '''
class ProjectContext:
    """ctx"""
    project = "demo"
    description = "test"
    environment = {"stato": "0.5.0", "scanpy": "1.10"}
'''

CTX_CURRENT = f'''
class ProjectContext:
    """ctx"""
    project = "demo"
    description = "test"
    environment = {{"stato": "{__version__}"}}
'''


def _proj(tmp_path, ctx=None):
    init_project(tmp_path)
    write_module(tmp_path, "plan.py", VALID_PLAN)
    write_module(tmp_path, "memory.py", VALID_MEMORY)
    if ctx:
        write_module(tmp_path, "context.py", ctx)
    return tmp_path


def test_resume_shows_version(tmp_path):
    _proj(tmp_path)
    text = generate_resume(tmp_path / ".stato")
    assert f"Stato: {__version__}" in text


def test_resume_version_mismatch_warns(tmp_path):
    _proj(tmp_path, CTX_STALE)
    text = generate_resume(tmp_path / ".stato")
    assert "version mismatch" in text
    assert "0.5.0" in text


def test_resume_no_warning_when_current(tmp_path):
    _proj(tmp_path, CTX_CURRENT)
    text = generate_resume(tmp_path / ".stato")
    assert "version mismatch" not in text


def test_resume_shows_mtime_freshness(tmp_path):
    _proj(tmp_path)
    text = generate_resume(tmp_path / ".stato")
    assert "State files last modified:" in text


def test_brief_includes_version(tmp_path):
    _proj(tmp_path, CTX_STALE)
    text = generate_resume(tmp_path / ".stato", brief=True)
    assert f"Stato: {__version__}" in text
    assert "version mismatch" in text


def test_status_shows_version(tmp_path):
    _proj(tmp_path)
    result = CliRunner().invoke(main, ["status", "--json", "--path", str(tmp_path)])
    payload = json.loads(result.output)
    assert payload["stato_version"] == __version__


def test_doctor_json(tmp_path):
    _proj(tmp_path)
    result = CliRunner().invoke(main, ["doctor", "--json", "--path", str(tmp_path)])
    assert result.exit_code == 0
    info = json.loads(result.output)
    assert info["version"] == __version__
    assert info["stato_dir_present"] is True
    assert info["modules"] >= 2
    assert "resolved_binary" in info


def test_doctor_uninitialized(tmp_path):
    result = CliRunner().invoke(main, ["doctor", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "not initialized" in result.output


def test_auto_stamp_off_by_default(tmp_path):
    init_project(tmp_path)
    sm = StateManager(tmp_path, history_keep=10)  # explicit -> auto_stamp False
    sm.write("skills/qc.py", VALID_QC_SKILL)
    src = (tmp_path / ".stato" / "skills" / "qc.py").read_text()
    assert "updated_at" not in src


def test_auto_stamp_when_requested(tmp_path):
    init_project(tmp_path)
    sm = StateManager(tmp_path, history_keep=10)
    sm.write("skills/qc.py", VALID_QC_SKILL, stamp=True)
    src = (tmp_path / ".stato" / "skills" / "qc.py").read_text()
    assert "updated_at" in src
    # still valid after stamping
    from stato.core.compiler import validate
    assert validate(src).success


def test_auto_stamp_via_config(tmp_path, monkeypatch):
    monkeypatch.setenv("STATO_CONFIG_DIR", str(tmp_path / "conf"))
    init_project(tmp_path)
    (tmp_path / ".stato" / "config.toml").write_text("[state]\nauto_stamp = true\n")
    sm = StateManager(tmp_path)  # reads config -> auto_stamp True
    sm.write("skills/qc.py", VALID_QC_SKILL)
    assert "updated_at" in (tmp_path / ".stato" / "skills" / "qc.py").read_text()


def test_stamp_updated_at_replaces_existing():
    from stato.core.edits import stamp_updated_at

    src = 'class Q:\n    """d"""\n    name="q"\n    updated_at = "2020-01-01"\n'
    out = stamp_updated_at(src, "2026-07-03")
    assert "2026-07-03" in out
    assert "2020-01-01" not in out
