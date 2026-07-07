"""Tests for the task-conditioned workspace (v0.10)."""
import json

from click.testing import CliRunner

from stato.cli import main
from stato.core.state_manager import init_project, write_module
from stato.core.workspace import assemble_workspace

QC = '''
class QC:
    """Quality control filtering for scRNA-seq."""
    name = "qc_filtering"
    version = "1.0.0"
    tags = ["scrna", "qc"]
    lessons_learned = "- mito threshold matters"
    def run(self):
        pass
'''

CLUSTER = '''
class Clustering:
    """Leiden clustering and UMAP."""
    name = "clustering"
    version = "1.0.0"
    tags = ["scrna", "clustering", "leiden"]
    def run(self):
        pass
'''

DEPLOY = '''
class Deploy:
    """Deployment and packaging."""
    name = "deployment"
    version = "1.0.0"
    tags = ["devops", "packaging"]
    def run(self):
        pass
'''

SAFETY_PINNED = '''
class Safety:
    """House safety and review conventions."""
    name = "safety_rules"
    version = "1.0.0"
    always_load = True
    lessons_learned = "- always validate before writing"
    def run(self):
        pass
'''


def _proj(tmp_path, skills, plan=None, context=None):
    init_project(tmp_path)
    for name, src in skills.items():
        write_module(tmp_path, f"skills/{name}.py", src)
    if plan:
        write_module(tmp_path, "plan.py", plan)
    if context:
        write_module(tmp_path, "context.py", context)
    return tmp_path


def test_task_query_ranks_relevant_first(tmp_path):
    _proj(tmp_path, {"qc": QC, "cluster": CLUSTER, "deploy": DEPLOY})
    view = assemble_workspace(tmp_path / ".stato", task="leiden clustering umap")
    assert view.signal == "task"
    assert view.active[0].name == "clustering"
    assert view.active[0].reason == "task match"


def test_active_carries_summary_not_full_source(tmp_path):
    _proj(tmp_path, {"qc": QC})
    view = assemble_workspace(tmp_path / ".stato", task="qc filtering")
    item = view.active[0]
    assert "###" in item.summary  # rendered summary marker
    assert "def run" not in item.summary  # not the raw source


def test_cold_fallback_to_plan_skills_used(tmp_path):
    plan = '''
class P:
    """plan"""
    name = "p"
    objective = "analyze"
    steps = [{"id": 1, "action": "cluster", "status": "running", "skills_used": ["clustering"]}]
'''
    _proj(tmp_path, {"qc": QC, "cluster": CLUSTER, "deploy": DEPLOY}, plan=plan)
    view = assemble_workspace(tmp_path / ".stato")  # no task
    assert view.signal == "plan"
    assert any(i.name == "clustering" and i.reason == "plan step" for i in view.active)


def test_cold_fallback_step_without_skills_used_uses_query(tmp_path):
    plan = '''
class P:
    """plan"""
    name = "p"
    objective = "single cell clustering with leiden"
    steps = [{"id": 1, "action": "run leiden clustering", "status": "running"}]
'''
    _proj(tmp_path, {"qc": QC, "cluster": CLUSTER, "deploy": DEPLOY}, plan=plan)
    view = assemble_workspace(tmp_path / ".stato")
    assert view.signal == "plan"
    assert view.active[0].name == "clustering"  # ranked from action/objective


def test_no_task_no_plan_index_only(tmp_path):
    _proj(tmp_path, {"qc": QC, "cluster": CLUSTER})
    view = assemble_workspace(tmp_path / ".stato")
    assert view.signal == "none"
    assert view.active == []
    assert {e["name"] for e in view.index} == {"qc_filtering", "clustering"}


def test_pin_always_active_even_off_task(tmp_path):
    _proj(tmp_path, {"qc": QC, "safety": SAFETY_PINNED})
    view = assemble_workspace(tmp_path / ".stato", task="clustering umap")
    names = {i.name for i in view.active}
    assert "safety_rules" in names
    assert next(i for i in view.active if i.name == "safety_rules").reason == "pinned"


def test_context_pinned_skills(tmp_path):
    ctx = '''
class C:
    """ctx"""
    project = "demo"
    description = "test"
    pinned_skills = ["qc_filtering"]
'''
    _proj(tmp_path, {"qc": QC, "cluster": CLUSTER}, context=ctx)
    view = assemble_workspace(tmp_path / ".stato", task="deployment devops")
    assert any(i.name == "qc_filtering" and i.reason == "pinned" for i in view.active)


def test_max_items_caps_non_pins(tmp_path):
    skills = {f"s{i}": QC.replace('"qc_filtering"', f'"skill_{i}"') for i in range(10)}
    _proj(tmp_path, skills)
    view = assemble_workspace(tmp_path / ".stato", task="quality control", max_items=3)
    non_pins = [i for i in view.active if i.reason != "pinned"]
    assert len(non_pins) <= 3


def test_pins_survive_budget(tmp_path):
    _proj(tmp_path, {"qc": QC, "cluster": CLUSTER, "safety": SAFETY_PINNED})
    # tiny budget: pins must still appear
    view = assemble_workspace(tmp_path / ".stato", task="clustering", budget=1)
    assert any(i.name == "safety_rules" for i in view.active)


def test_index_excludes_active(tmp_path):
    _proj(tmp_path, {"qc": QC, "cluster": CLUSTER, "deploy": DEPLOY})
    view = assemble_workspace(tmp_path / ".stato", task="leiden clustering")
    active_names = {i.name for i in view.active}
    index_names = {e["name"] for e in view.index}
    assert active_names.isdisjoint(index_names)


def test_render_and_to_dict(tmp_path):
    _proj(tmp_path, {"qc": QC})
    view = assemble_workspace(tmp_path / ".stato", task="qc")
    text = view.render()
    assert "Workspace for: qc" in text
    d = view.to_dict()
    assert d["signal"] == "task" and d["active"]


def test_always_load_validates():
    from stato.core.compiler import validate
    assert validate(SAFETY_PINNED, expected_type="skill").success


def test_pinned_skills_validates():
    from stato.core.compiler import validate
    ctx = 'class C:\n    """c"""\n    project="p"\n    description="d"\n    pinned_skills=["a","b"]\n'
    assert validate(ctx).success


def test_cli_workspace_json(tmp_path):
    _proj(tmp_path, {"qc": QC, "cluster": CLUSTER})
    result = CliRunner().invoke(
        main, ["workspace", "leiden clustering", "--json", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["signal"] == "task"
    assert payload["active"][0]["name"] == "clustering"


def test_cli_workspace_text(tmp_path):
    _proj(tmp_path, {"qc": QC})
    result = CliRunner().invoke(main, ["workspace", "qc", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "Active skills" in result.output


def test_team_body_references_workspace(tmp_path):
    _proj(tmp_path, {"qc": QC})
    (tmp_path / ".stato" / "team.toml").write_text(
        '[agents.analyst]\ndescription = "d"\nskills = ["qc_filtering"]\n'
    )
    from stato.team import assemble
    assemble(tmp_path, formats=["claude"])
    body = (tmp_path / ".claude" / "agents" / "analyst.md").read_text()
    assert "stato_workspace(task)" in body
