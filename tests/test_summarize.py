"""Tests for progressive disclosure: summarize, migrate-lessons, team --inline."""
import io
import json

from click.testing import CliRunner

from stato.cli import main
from stato.core.edits import migrate_lessons
from stato.core.state_manager import init_project, write_module
from stato.core.summarize import (
    get_skill_section,
    render_summary,
    summarize_module,
)

STRUCTURED_SKILL = '''
class BatchCorrection:
    """Batch effect correction for scRNA-seq."""
    name = "batch_correction"
    version = "1.0.0"
    tags = ["scrna", "integration"]
    default_params = {"method": "harmony", "n_pcs": 30}
    lessons = [
        {"condition": "n_batches > 5", "recommendation": "use harmony"},
        {"condition": "shared cell types", "recommendation": "use scVI"},
    ]
    def run(self, adata, method: str = "harmony") -> dict:
        return {}
'''

PROSE_SKILL = '''
class QC:
    """Quality control."""
    name = "qc"
    version = "1.0.0"
    lessons_learned = """
    - First lesson about mito
      continues on second line
    - Second lesson about genes
    - Third lesson
    """
    def run(self):
        pass
'''


def test_summary_from_structured():
    s = summarize_module(STRUCTURED_SKILL)
    assert s.name == "batch_correction"
    assert s.module_type == "skill"
    assert "harmony" in " ".join(s.params) or "method" in s.params
    assert len(s.lessons) == 2
    assert s.lessons[0].title == "n_batches > 5"
    assert "run(adata, method) -> dict" in " ".join(s.signatures)


def test_summary_from_prose():
    s = summarize_module(PROSE_SKILL)
    assert len(s.lessons) == 3
    assert "First lesson about mito" in s.lessons[0].title
    # multi-line bullet keeps its continuation in full text
    assert "continues on second line" in s.lessons[0].text


def test_render_summary_is_compact():
    s = summarize_module(STRUCTURED_SKILL)
    text = render_summary(s)
    assert "Lessons index" in text
    assert "[0]" in text and "[1]" in text
    assert "stato_get_skill_section" in text
    # much smaller than the full source
    assert len(text) < len(STRUCTURED_SKILL)


def test_get_skill_section():
    assert "use harmony" in get_skill_section(STRUCTURED_SKILL, 0)
    assert "use scVI" in get_skill_section(STRUCTURED_SKILL, 1)
    assert get_skill_section(STRUCTURED_SKILL, 99) is None


def test_migrate_prose_to_structured():
    from stato.core.astload import load_class
    from stato.core.compiler import validate

    new = migrate_lessons(PROSE_SKILL)
    assert new != PROSE_SKILL
    assert validate(new).success
    cls = load_class(new)
    assert len(cls.lessons) == 3
    assert cls.lessons[0]["recommendation"].startswith("First lesson about mito")
    # prose kept (non-destructive)
    assert cls.lessons_learned


def test_migrate_noop_when_already_structured():
    assert migrate_lessons(STRUCTURED_SKILL) == STRUCTURED_SKILL


def test_migrate_lessons_cli(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", PROSE_SKILL)
    result = CliRunner().invoke(
        main, ["migrate-lessons", str(tmp_path / ".stato")]
    )
    assert result.exit_code == 0
    from stato.core.astload import load_class
    cls = load_class((tmp_path / ".stato" / "skills" / "qc.py").read_text())
    assert isinstance(cls.lessons, list) and len(cls.lessons) == 3


def test_team_default_uses_lessons_index(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", STRUCTURED_SKILL)
    (tmp_path / ".stato" / "team.toml").write_text(
        '[agents.analyst]\ndescription = "d"\nskills = ["batch_correction"]\n'
    )
    from stato.team import assemble
    assemble(tmp_path, formats=["claude"])
    body = (tmp_path / ".claude" / "agents" / "analyst.md").read_text()
    assert "Lessons index" in body
    assert "stato_get_skill_section" in body
    # NOT the full source inlined
    assert "```python" not in body


def test_team_inline_embeds_source(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", STRUCTURED_SKILL)
    (tmp_path / ".stato" / "team.toml").write_text(
        '[agents.analyst]\ndescription = "d"\nskills = ["batch_correction"]\n'
    )
    from stato.team import assemble
    assemble(tmp_path, formats=["claude"], inline=True)
    body = (tmp_path / ".claude" / "agents" / "analyst.md").read_text()
    assert "```python" in body
    assert "class BatchCorrection" in body


def test_reminder_rate_gate(tmp_path, monkeypatch):
    from stato.hooks import payloads

    monkeypatch.setenv("STATO_CONFIG_DIR", str(tmp_path / "conf"))
    init_project(tmp_path)
    (tmp_path / ".stato" / "config.toml").write_text(
        "[hooks]\nreminder_threshold = 1\nreminder_min_interval = 60\n"
    )
    steps = [{"id": 1, "action": "a", "status": "complete", "output": "x"},
             {"id": 2, "action": "b", "status": "complete", "output": "y"}]
    write_module(tmp_path, "plan.py",
                 f'class P:\n    """p"""\n    name="p"\n    objective="x"\n    steps={steps!r}\n')
    # first fires
    out = io.StringIO()
    payloads.stop_reminder({"cwd": str(tmp_path)}, out=out)
    assert "systemMessage" in json.loads(out.getvalue())
    # progress more, but within the 60-min interval -> silent
    steps.append({"id": 3, "action": "c", "status": "complete", "output": "z"})
    write_module(tmp_path, "plan.py",
                 f'class P:\n    """p"""\n    name="p"\n    objective="x"\n    steps={steps!r}\n')
    out2 = io.StringIO()
    payloads.stop_reminder({"cwd": str(tmp_path)}, out=out2)
    assert out2.getvalue() == "{}"


def test_resume_staleness_warning(tmp_path):
    import os
    import time

    from stato.core.resume import generate_resume

    init_project(tmp_path)
    write_module(tmp_path, "memory.py",
                 'class S:\n    """s"""\n    phase="x"\n    reflection="did things."\n')
    # backdate all .stato modules 30 days
    old = time.time() - 30 * 86400
    for p in (tmp_path / ".stato").rglob("*.py"):
        os.utime(p, (old, old))
    text = generate_resume(tmp_path / ".stato")
    assert "may be stale" in text
