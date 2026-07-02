"""Tests for atomic writes, locking, and history retention (WS3)."""
import multiprocessing
from pathlib import Path

from stato.core.state_manager import StateManager, _atomic_write_text, init_project
from tests.fixtures import VALID_QC_SKILL


def _make_skill(name: str, version: str = "1.0.0") -> str:
    return f'''
class Skill_{name}:
    """Generated test skill."""
    name = "{name}"
    version = "{version}"

    def run(self):
        pass
'''


def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "sub" / "file.py"
    _atomic_write_text(target, "content")
    assert target.read_text() == "content"


def test_atomic_write_no_temp_leftovers(tmp_path):
    target = tmp_path / "file.py"
    _atomic_write_text(target, "one")
    _atomic_write_text(target, "two")
    assert target.read_text() == "two"
    leftovers = [p for p in tmp_path.iterdir() if p.name != "file.py"]
    assert leftovers == []


def test_write_is_validate_gated_still(tmp_path):
    init_project(tmp_path)
    sm = StateManager(tmp_path, history_keep=5)
    result = sm.write("skills/bad.py", "not python at all (")
    assert not result.success
    assert not (tmp_path / ".stato" / "skills" / "bad.py").exists()


def test_history_pruning(tmp_path):
    init_project(tmp_path)
    sm = StateManager(tmp_path, history_keep=3)
    for i in range(8):
        r = sm.write("skills/qc.py", _make_skill("qc", f"1.0.{i}"))
        assert r.success
    backups = list((tmp_path / ".stato" / ".history").glob("qc.*.py"))
    assert len(backups) <= 3


def test_history_keep_zero_disables_pruning(tmp_path):
    init_project(tmp_path)
    sm = StateManager(tmp_path, history_keep=0)
    for i in range(4):
        sm.write("skills/qc.py", _make_skill("qc", f"1.0.{i}"))
    backups = list((tmp_path / ".stato" / ".history").glob("qc.*.py"))
    assert len(backups) == 3  # 4 writes -> 3 backups, none pruned


def _writer_proc(project_dir: str, idx: int, n: int):
    sm = StateManager(Path(project_dir), history_keep=100)
    for i in range(n):
        result = sm.write(f"skills/w{idx}.py", _make_skill(f"w{idx}", f"1.{i}.0"))
        assert result.success


def test_concurrent_writers_no_corruption(tmp_path):
    """Two processes writing concurrently: all files valid at the end."""
    init_project(tmp_path)
    procs = [
        multiprocessing.Process(target=_writer_proc, args=(str(tmp_path), i, 10))
        for i in range(2)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0

    from stato.core.compiler import validate

    for i in range(2):
        target = tmp_path / ".stato" / "skills" / f"w{i}.py"
        assert target.exists()
        assert validate(target.read_text()).success


def test_concurrent_same_file(tmp_path):
    """Two processes hammering the same module: final content is one valid write."""
    init_project(tmp_path)
    procs = [
        multiprocessing.Process(target=_writer_proc, args=(str(tmp_path), 9, 10))
        for _ in range(2)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0

    from stato.core.compiler import validate

    content = (tmp_path / ".stato" / "skills" / "w9.py").read_text()
    assert validate(content).success


def test_rollback_still_works(tmp_path):
    init_project(tmp_path)
    sm = StateManager(tmp_path, history_keep=10)
    sm.write("skills/qc.py", VALID_QC_SKILL)
    sm.write("skills/qc.py", _make_skill("qc", "2.0.0"))
    assert sm.rollback("skills/qc.py") is True
    assert (tmp_path / ".stato" / "skills" / "qc.py").read_text() == VALID_QC_SKILL
