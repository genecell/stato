"""Tests for `stato reflect` — dead-end evidence from edit history (v0.11)."""
import json

from click.testing import CliRunner

from stato.cli import main
from stato.core.reflect import reflect
from stato.core.state_manager import StateManager, init_project


def _skill(param_val, version="1.0.0"):
    return f'''
class QC:
    """Quality control."""
    name = "qc"
    version = "{version}"
    default_params = {{"max_pct_mito": {param_val}}}
    def run(self):
        pass
'''


def _history_of(tmp_path, values, keep=50):
    """Write a skill repeatedly so .history/ records the value sequence."""
    init_project(tmp_path)
    sm = StateManager(tmp_path, history_keep=keep)
    for v in values:
        sm.write("skills/qc.py", _skill(v))
    return tmp_path


def test_reversion_detected(tmp_path):
    _history_of(tmp_path, [20, 25, 20])  # tried 25, reverted to 20
    report = reflect(tmp_path / ".stato")
    revs = [c for c in report.candidates if c.field == "default_params.max_pct_mito"]
    assert revs and revs[0].signal == "reversion"
    assert "20" in revs[0].evidence and "25" in revs[0].evidence


def test_no_reversion_for_monotonic_but_churn_if_over_threshold(tmp_path):
    _history_of(tmp_path, [10, 20, 30, 40])  # only moves forward
    report = reflect(tmp_path / ".stato", min_churn=3)
    cands = {c.field: c for c in report.candidates}
    c = cands.get("default_params.max_pct_mito")
    assert c is not None and c.signal == "churn"  # 3 changes, never reverts


def test_stable_field_no_candidate(tmp_path):
    _history_of(tmp_path, [20, 20, 20])  # never changed
    report = reflect(tmp_path / ".stato")
    assert not any(c.field == "default_params.max_pct_mito" for c in report.candidates)


def test_below_churn_threshold_silent(tmp_path):
    _history_of(tmp_path, [20, 25])  # one change, no reversion
    report = reflect(tmp_path / ".stato", min_churn=3)
    assert not report.candidates


def test_version_reversion(tmp_path):
    init_project(tmp_path)
    sm = StateManager(tmp_path, history_keep=50)
    for v in ["1.0.0", "2.0.0", "1.0.0"]:
        sm.write("skills/qc.py", _skill(20, version=v))
    report = reflect(tmp_path / ".stato")
    assert any(c.field == "version" and c.signal == "reversion"
               for c in report.candidates)


def test_narrative_fields_skipped(tmp_path):
    """Long prose (reflection) churning must not produce candidates."""
    init_project(tmp_path)
    sm = StateManager(tmp_path, history_keep=50)
    for phase in ["a", "b", "a"]:
        sm.write("memory.py",
                 f'class S:\n    """s"""\n    phase="{phase}"\n'
                 f'    reflection="{"x" * 200} v{phase}"\n')
    report = reflect(tmp_path / ".stato")
    assert not any(c.field == "reflection" for c in report.candidates)
    # short scalar `phase` still analyzed
    assert any(c.field == "phase" for c in report.candidates)


def test_no_history_no_candidates(tmp_path):
    init_project(tmp_path)
    StateManager(tmp_path).write("skills/qc.py", _skill(20))  # single write, no prior
    report = reflect(tmp_path / ".stato")
    assert not report.candidates


def test_reversions_sorted_first(tmp_path):
    init_project(tmp_path)
    sm = StateManager(tmp_path, history_keep=50)
    # qc reverts; norm just churns
    for v in [20, 25, 20]:
        sm.write("skills/qc.py", _skill(v))
    for v in ["1.0", "1.1", "1.2", "1.3"]:
        sm.write("skills/norm.py",
                 f'class N:\n    """n"""\n    name="norm"\n    version="{v}.0"\n'
                 f'    default_params={{"k": 1}}\n    def run(self): pass\n')
    report = reflect(tmp_path / ".stato", min_churn=3)
    assert report.candidates[0].signal == "reversion"


def test_render_and_json(tmp_path):
    _history_of(tmp_path, [20, 25, 20])
    report = reflect(tmp_path / ".stato")
    text = report.render()
    assert "candidate lessons" in text
    assert "reverted" in text
    d = report.to_dict()
    assert d["candidates"] and d["candidates"][0]["signal"] == "reversion"


def test_cli_reflect_json(tmp_path):
    _history_of(tmp_path, [20, 25, 20])
    result = CliRunner().invoke(main, ["reflect", "--json", "--path", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert any(c["signal"] == "reversion" for c in payload["candidates"])


def test_cli_reflect_empty(tmp_path):
    init_project(tmp_path)
    result = CliRunner().invoke(main, ["reflect", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "nothing to reflect" in result.output.lower()


def test_prompt_mentions_pitfalls():
    from stato.prompts import get_crystallize_prompt
    p = get_crystallize_prompt()
    assert "pitfall" in p.lower() or "dead-end" in p.lower()
    assert "stato reflect" in p
