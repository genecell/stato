"""Tests for `stato team assemble` (v0.7 spike)."""
import json

import pytest
from click.testing import CliRunner

from stato.cli import main
from stato.core.state_manager import init_project, write_module
from stato.team import (
    TeamSpecError,
    assemble,
    parse_team_spec,
    resolve_agent_skills,
)

QC_SKILL = '''
class QualityControl:
    """QC filtering."""
    name = "qc_filtering"
    version = "1.2.0"
    default_params = {"min_genes": 200}
    def run(self): pass
'''

CLUSTER_SKILL = '''
class Clustering:
    """Leiden clustering."""
    name = "clustering"
    version = "1.0.0"
    depends_on = ["qc_filtering"]
    def run(self): pass
'''

LOAD_SKILL = '''
class DataLoading:
    """Load datasets."""
    name = "data_loading"
    version = "1.1.0"
    def run(self): pass
'''

TEAM_TOML = '''
[team]
name = "scrna-pipeline"
description = "single cell team"

[agents.data_engineer]
description = "Loads and preprocesses data"
skills = ["data_loading"]
model = "sonnet"
tools = ["Read", "Bash"]
handoff = "Hand the processed dataset to the analyst."

[agents.analyst]
description = "QC and clustering"
skills = ["qc_filtering", "clustering"]
'''


@pytest.fixture
def project(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "skills/qc.py", QC_SKILL)
    write_module(tmp_path, "skills/cluster.py", CLUSTER_SKILL)
    write_module(tmp_path, "skills/load.py", LOAD_SKILL)
    (tmp_path / ".stato" / "team.toml").write_text(TEAM_TOML)
    return tmp_path


def test_parse_valid_spec(project):
    spec = parse_team_spec(project / ".stato" / "team.toml")
    assert spec.name == "scrna-pipeline"
    assert {a.role for a in spec.agents} == {"data_engineer", "analyst"}
    de = next(a for a in spec.agents if a.role == "data_engineer")
    assert de.model == "sonnet"
    assert de.tools == ["Read", "Bash"]
    assert de.handoff


def test_missing_skills_field_errors(tmp_path):
    (tmp_path / "team.toml").write_text(
        '[agents.x]\ndescription = "no skills"\n'
    )
    with pytest.raises(TeamSpecError, match="non-empty 'skills'"):
        parse_team_spec(tmp_path / "team.toml")


def test_missing_description_errors(tmp_path):
    (tmp_path / "team.toml").write_text(
        '[agents.x]\nskills = ["a"]\n'
    )
    with pytest.raises(TeamSpecError, match="description"):
        parse_team_spec(tmp_path / "team.toml")


def test_no_agents_errors(tmp_path):
    (tmp_path / "team.toml").write_text('[team]\nname = "x"\n')
    with pytest.raises(TeamSpecError, match="no \\[agents"):
        parse_team_spec(tmp_path / "team.toml")


def test_unknown_skill_errors(project):
    (project / ".stato" / "team.toml").write_text(
        '[agents.x]\ndescription = "d"\nskills = ["nonexistent"]\n'
    )
    spec = parse_team_spec(project / ".stato" / "team.toml")
    with pytest.raises(TeamSpecError, match="unknown skill 'nonexistent'"):
        resolve_agent_skills(project / ".stato", spec.agents[0])


def test_resolve_by_name_and_stem(project):
    spec = parse_team_spec(project / ".stato" / "team.toml")
    analyst = next(a for a in spec.agents if a.role == "analyst")
    # referenced by `name` field
    mods = resolve_agent_skills(project / ".stato", analyst)
    names = {m["namespace"][m["class_name"]].name for m in mods}
    assert names == {"qc_filtering", "clustering"}

    # referenced by file stem
    analyst.skills = ["qc", "cluster"]
    mods2 = resolve_agent_skills(project / ".stato", analyst)
    assert {m["namespace"][m["class_name"]].name for m in mods2} == {"qc_filtering", "clustering"}


def test_with_deps_pulls_dependencies(project):
    from stato.team import AgentSpec

    agent = AgentSpec(role="c", description="d", skills=["clustering"], with_deps=True)
    mods = resolve_agent_skills(project / ".stato", agent)
    names = {m["namespace"][m["class_name"]].name for m in mods}
    assert "clustering" in names and "qc_filtering" in names  # dep pulled in

    agent_nodep = AgentSpec(role="c", description="d", skills=["clustering"])
    names_nodep = {
        m["namespace"][m["class_name"]].name
        for m in resolve_agent_skills(project / ".stato", agent_nodep)
    }
    assert names_nodep == {"clustering"}


def test_render_has_valid_frontmatter(project):
    assemble(project, formats=["claude"])
    de = project / ".claude" / "agents" / "data_engineer.md"
    content = de.read_text()
    assert content.startswith("---\n")
    assert "name: data_engineer" in content
    assert "description: Loads and preprocesses data" in content
    assert "model: sonnet" in content
    assert "tools: Read, Bash" in content


def test_render_scopes_skills(project):
    assemble(project, formats=["claude"])
    de = (project / ".claude" / "agents" / "data_engineer.md").read_text()
    an = (project / ".claude" / "agents" / "analyst.md").read_text()
    assert "data_loading" in de and "qc_filtering" not in de
    assert "qc_filtering" in an and "clustering" in an
    assert "data_loading" not in an


def test_render_includes_handoff(project):
    assemble(project, formats=["claude"])
    de = (project / ".claude" / "agents" / "data_engineer.md").read_text()
    an = (project / ".claude" / "agents" / "analyst.md").read_text()
    assert "## Handoff" in de and "hand the processed dataset" in de.lower()
    assert "## Handoff" not in an  # analyst has no handoff


def test_marker_present(project):
    assemble(project, formats=["claude"])
    content = (project / ".claude" / "agents" / "analyst.md").read_text()
    assert "Generated by stato team assemble" in content


def test_all_formats_native_shapes(project):
    assemble(project, formats=["claude", "codex", "gemini", "sdk"])

    # Claude: markdown + YAML frontmatter, tools passthrough
    claude = (project / ".claude" / "agents" / "data_engineer.md").read_text()
    assert claude.startswith("---\n") and "tools: Read, Bash" in claude

    # Gemini: markdown + frontmatter, but NO Claude tool names
    gemini = (project / ".gemini" / "agents" / "data_engineer.md").read_text()
    assert gemini.startswith("---\n")
    assert "tools:" not in gemini  # Claude tool names would be invalid for Gemini

    # Codex: TOML with developer_instructions (not markdown)
    codex_path = project / ".codex" / "agents" / "analyst.toml"
    assert codex_path.exists()
    import tomli

    codex = tomli.loads(codex_path.read_text())
    assert codex["name"] == "analyst"
    assert "qc_filtering" in codex["developer_instructions"]
    assert "developer_instructions" in codex

    # SDK: JSON config
    sdk = project / ".stato" / "team" / "analyst.agent.json"
    cfg = json.loads(sdk.read_text())
    assert cfg["name"] == "analyst"
    assert "prompt" in cfg and "qc_filtering" in cfg["prompt"]


def test_codex_toml_is_valid_and_marked(project):
    import tomli

    assemble(project, formats=["codex"])
    path = project / ".codex" / "agents" / "data_engineer.toml"
    text = path.read_text()
    assert text.startswith(f"# {__import__('stato.team', fromlist=['TEAM_MARKER']).TEAM_MARKER}")
    parsed = tomli.loads(text)  # must be valid TOML despite the comment
    assert parsed["description"]
    assert parsed["model"] == "sonnet"


def test_dry_run_writes_nothing(project):
    results = assemble(project, formats=["claude"], dry_run=True)
    assert all(action == "would-write" for _, action in results)
    assert not (project / ".claude" / "agents").exists()


def test_merge_not_overwrite(project):
    agents_dir = project / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    handwritten = agents_dir / "analyst.md"
    handwritten.write_text("my own agent, do not touch\n")

    results = assemble(project, formats=["claude"])
    actions = {p.name: a for p, a in results}
    assert actions["analyst.md"] == "skipped"
    assert handwritten.read_text() == "my own agent, do not touch\n"
    # regenerating a stato-owned file IS allowed
    assert actions["data_engineer.md"] == "created"


def test_force_overwrites_handwritten(project):
    agents_dir = project / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "analyst.md").write_text("mine\n")
    results = assemble(project, formats=["claude"], force=True)
    actions = {p.name: a for p, a in results}
    assert actions["analyst.md"] == "overwritten"


def test_unknown_skill_aborts_before_writing(project):
    (project / ".stato" / "team.toml").write_text(
        TEAM_TOML + '\n[agents.broken]\ndescription = "d"\nskills = ["ghost"]\n'
    )
    with pytest.raises(TeamSpecError):
        assemble(project, formats=["claude"])
    # nothing written because resolution happens before any write
    assert not (project / ".claude" / "agents").exists()


def test_cli_end_to_end(project):
    result = CliRunner().invoke(
        main, ["team", "assemble", "--path", str(project)]
    )
    assert result.exit_code == 0
    assert (project / ".claude" / "agents" / "data_engineer.md").exists()
    assert (project / ".claude" / "agents" / "analyst.md").exists()


def test_cli_unknown_skill_exit_1(project):
    (project / ".stato" / "team.toml").write_text(
        '[agents.x]\ndescription = "d"\nskills = ["ghost"]\n'
    )
    result = CliRunner().invoke(main, ["team", "assemble", "--path", str(project)])
    assert result.exit_code == 1
    assert "unknown skill" in result.output
