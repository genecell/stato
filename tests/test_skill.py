"""Tests for the canonical stato Agent Skill + `stato skill install` (Tier 1+2)."""
import re
from pathlib import Path

from click.testing import CliRunner

from stato.cli import main
from stato.skill_doc import (
    SKILL_NAME,
    all_tools,
    render_skill_md,
    skill_target_dir,
)

REPO_SKILL = Path(__file__).parent.parent / "skills" / "stato" / "SKILL.md"


def _split_frontmatter(text: str) -> dict:
    """Parse the ---fenced YAML header into a shallow dict (no YAML dep)."""
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    header = text[4:end]
    fields = {}
    for line in header.splitlines():
        if line and not line.startswith((" ", "\t")) and ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()
    return fields


def test_name_matches_spec_pattern():
    fm = _split_frontmatter(render_skill_md())
    assert fm["name"] == SKILL_NAME
    assert re.match(r"^[a-z0-9-]{1,64}$", fm["name"])


def test_description_present_and_bounded():
    fm = _split_frontmatter(render_skill_md())
    assert fm["description"]
    assert len(fm["description"]) <= 1024


def test_version_and_author_under_metadata_not_toplevel():
    text = render_skill_md(version="9.9.9")
    fm = _split_frontmatter(text)
    # version/author are NOT first-class spec fields
    assert "version" not in fm
    assert "author" not in fm
    # they live under metadata
    assert "metadata:" in text
    assert '9.9.9' in text
    assert "author: Stato" in text


def test_license_field():
    assert "license: MIT" in render_skill_md()


def test_body_teaches_operating_loop():
    text = render_skill_md()
    for needle in ("stato resume", "stato validate", "operating loop",
                   "module schemas", "stato mcp", "hooks install"):
        assert needle.lower() in text.lower(), needle


def test_repo_file_matches_constant():
    """Drift guard: skills/stato/SKILL.md must equal render_skill_md()."""
    assert REPO_SKILL.exists(), "run: stato skill show > skills/stato/SKILL.md"
    assert REPO_SKILL.read_text() == render_skill_md()


def test_target_dir_project_scope(tmp_path):
    d = skill_target_dir("claude", user=False, project_dir=tmp_path)
    assert d == tmp_path / ".claude" / "skills" / "stato"


def test_target_dir_all_tools(tmp_path):
    expected = {
        "claude": ".claude", "codex": ".codex",
        "cursor": ".cursor", "gemini": ".gemini",
    }
    for tool, top in expected.items():
        d = skill_target_dir(tool, user=False, project_dir=tmp_path)
        assert d == tmp_path / top / "skills" / "stato"
    assert set(all_tools()) == set(expected)


def test_target_dir_user_scope(tmp_path):
    d = skill_target_dir("gemini", user=True, project_dir=tmp_path)
    assert str(d).startswith(str(Path.home()))
    assert d.parts[-3:] == (".gemini", "skills", "stato")


def test_install_claude(tmp_path):
    result = CliRunner().invoke(
        main, ["skill", "install", "--tool", "claude", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    out = tmp_path / ".claude" / "skills" / "stato" / "SKILL.md"
    assert out.exists()
    assert out.read_text() == render_skill_md()


def test_install_all_tools(tmp_path):
    result = CliRunner().invoke(
        main, ["skill", "install", "--tool", "all", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    for top in (".claude", ".codex", ".cursor", ".gemini"):
        assert (tmp_path / top / "skills" / "stato" / "SKILL.md").exists()


def test_install_default_is_claude(tmp_path):
    result = CliRunner().invoke(main, ["skill", "install", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".claude" / "skills" / "stato" / "SKILL.md").exists()
    assert not (tmp_path / ".codex").exists()


def test_install_skips_non_stato_file(tmp_path):
    out_dir = tmp_path / ".claude" / "skills" / "stato"
    out_dir.mkdir(parents=True)
    (out_dir / "SKILL.md").write_text("hand-written, not stato\n")
    result = CliRunner().invoke(
        main, ["skill", "install", "--tool", "claude", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "Skipped" in result.output
    assert (out_dir / "SKILL.md").read_text() == "hand-written, not stato\n"


def test_install_force_overwrites(tmp_path):
    out_dir = tmp_path / ".claude" / "skills" / "stato"
    out_dir.mkdir(parents=True)
    (out_dir / "SKILL.md").write_text("hand-written\n")
    result = CliRunner().invoke(
        main, ["skill", "install", "--tool", "claude", "--force", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert (out_dir / "SKILL.md").read_text() == render_skill_md()


def test_reinstall_refreshes_stato_owned(tmp_path):
    CliRunner().invoke(main, ["skill", "install", "--path", str(tmp_path)])
    # second run overwrites our own file without --force (marker present)
    result = CliRunner().invoke(main, ["skill", "install", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "Skipped" not in result.output


def test_skill_show(tmp_path):
    result = CliRunner().invoke(main, ["skill", "show"])
    assert result.exit_code == 0
    assert "name: stato" in result.output
    assert "# Using stato" in result.output
