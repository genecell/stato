"""Tests for hook installers and payloads (WS8)."""
import io
import json

from click.testing import CliRunner

from stato.cli import main
from stato.core.state_manager import init_project, write_module
from stato.hooks import installers, payloads
from tests.fixtures import VALID_MEMORY


def test_claude_install_merges_not_overwrites(tmp_path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "hooks": {
            "PreCompact": [
                {"matcher": "manual", "hooks": [
                    {"type": "command", "command": "my-own-hook"}]}
            ]
        },
        "permissions": {"allow": ["Bash(ls)"]},
    }))

    installers.apply_writes(installers.plan_install(tmp_path, "claude"))
    data = json.loads(settings.read_text())

    # user's own settings preserved
    assert data["permissions"]["allow"] == ["Bash(ls)"]
    commands = [
        h["command"]
        for entries in data["hooks"].values()
        for e in entries for h in e["hooks"]
    ]
    assert "my-own-hook" in commands
    assert "stato hook pre-compact" in commands
    assert "stato hook session-start" in commands


def test_install_idempotent(tmp_path):
    installers.apply_writes(installers.plan_install(tmp_path, "claude"))
    first = (tmp_path / ".claude" / "settings.json").read_text()
    installers.apply_writes(installers.plan_install(tmp_path, "claude"))
    second = (tmp_path / ".claude" / "settings.json").read_text()
    assert first == second


def test_uninstall_removes_only_stato(tmp_path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "hooks": {
            "PreCompact": [
                {"matcher": "manual", "hooks": [
                    {"type": "command", "command": "my-own-hook"}]}
            ]
        }
    }))
    installers.apply_writes(installers.plan_install(tmp_path, "claude"))
    installers.apply_writes(installers.plan_install(tmp_path, "claude", uninstall=True))
    data = json.loads(settings.read_text())
    commands = [
        h["command"]
        for entries in data.get("hooks", {}).values()
        for e in entries for h in e["hooks"]
    ]
    assert "my-own-hook" in commands
    assert not any("stato hook" in c for c in commands)


def test_codex_install(tmp_path):
    installers.apply_writes(installers.plan_install(tmp_path, "codex"))
    data = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    assert "PreCompact" in data
    assert "PostCompact" in data


def test_gemini_install_hooks_and_extension(tmp_path):
    installers.apply_writes(installers.plan_install(tmp_path, "gemini"))
    settings = json.loads((tmp_path / ".gemini" / "settings.json").read_text())
    assert "PreCompress" in settings["hooks"]
    assert "SessionStart" in settings["hooks"]

    manifest = json.loads(
        (tmp_path / ".gemini" / "extensions" / "stato" / "gemini-extension.json").read_text()
    )
    assert manifest["mcpServers"]["stato"]["command"] == "stato"
    assert (tmp_path / ".gemini" / "extensions" / "stato" / "commands" / "stato" / "save.toml").exists()
    assert (tmp_path / ".gemini" / "extensions" / "stato" / "commands" / "stato" / "resume.toml").exists()


def test_status(tmp_path):
    assert installers.status(tmp_path) == {"claude": False, "codex": False, "gemini": False}
    installers.apply_writes(installers.plan_install(tmp_path, "claude"))
    assert installers.status(tmp_path)["claude"] is True


def test_install_via_cli_all(tmp_path):
    result = CliRunner().invoke(
        main, ["hooks", "install", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / ".codex" / "hooks.json").exists()
    assert (tmp_path / ".gemini" / "settings.json").exists()


def test_install_dry_run_writes_nothing(tmp_path):
    result = CliRunner().invoke(
        main, ["hooks", "install", "--platform", "claude", "--dry-run", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert not (tmp_path / ".claude").exists()


def test_hooks_status_cli_json(tmp_path):
    installers.apply_writes(installers.plan_install(tmp_path, "claude"))
    result = CliRunner().invoke(
        main, ["hooks", "status", "--json", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert json.loads(result.output)["claude"] is True


def test_pre_compact_payload_contract():
    out = io.StringIO()
    code = payloads.pre_compact({"trigger": "manual", "cwd": "/tmp"}, out=out)
    assert code == 0
    payload = json.loads(out.getvalue())
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreCompact"
    assert "additionalContext" in payload["hookSpecificOutput"]


def test_session_start_injects_resume(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "memory.py", VALID_MEMORY)
    out = io.StringIO()
    code = payloads.session_start({"cwd": str(tmp_path)}, out=out)
    assert code == 0
    payload = json.loads(out.getvalue())
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert "Restored stato project state" in ctx
    assert len(ctx.strip()) > len("Restored stato project state (validated, on-disk):")


def test_session_start_no_stato_is_noop(tmp_path):
    out = io.StringIO()
    code = payloads.session_start({"cwd": str(tmp_path)}, out=out)
    assert code == 0
    assert out.getvalue() == "{}"


def test_freshness_gate_blocks_when_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("STATO_CONFIG_DIR", str(tmp_path / "conf"))
    init_project(tmp_path)
    write_module(tmp_path, "memory.py", VALID_MEMORY)
    (tmp_path / ".stato" / "config.toml").write_text(
        "[hooks]\nfreshness_gate = true\n"
    )
    # transcript far newer than memory.py
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("{}")
    import os

    memory = tmp_path / ".stato" / "memory.py"
    old = memory.stat().st_mtime - 10000
    os.utime(memory, (old, old))

    out = io.StringIO()
    code = payloads.pre_compact(
        {"trigger": "auto", "cwd": str(tmp_path),
         "transcript_path": str(transcript)},
        out=out,
    )
    assert code == 2


def test_freshness_gate_off_by_default(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "memory.py", VALID_MEMORY)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}")
    out = io.StringIO()
    code = payloads.pre_compact(
        {"trigger": "auto", "cwd": str(tmp_path), "transcript_path": str(transcript)},
        out=out,
    )
    assert code == 0


# --- Stop-reminder (WS2) ---

def _plan_with_completed(n_complete, n_total=5):
    steps = []
    for i in range(1, n_total + 1):
        status = "complete" if i <= n_complete else "pending"
        step = {"id": i, "action": f"step{i}", "status": status}
        if status == "complete":
            step["output"] = "done"
        steps.append(step)
    lines = ["class P:", '    """plan"""', '    name = "p"', '    objective = "x"',
             f"    steps = {steps!r}"]
    return "\n".join(lines) + "\n"


def test_reminder_no_plan_noop(tmp_path):
    init_project(tmp_path)
    out = io.StringIO()
    assert payloads.stop_reminder({"cwd": str(tmp_path)}, out=out) == 0
    assert out.getvalue() == "{}"


def test_reminder_below_threshold_silent(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "plan.py", _plan_with_completed(2))  # threshold default 3
    out = io.StringIO()
    payloads.stop_reminder({"cwd": str(tmp_path)}, out=out)
    assert out.getvalue() == "{}"


def test_reminder_fires_at_threshold_and_advances(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "plan.py", _plan_with_completed(3))
    out = io.StringIO()
    payloads.stop_reminder({"cwd": str(tmp_path)}, out=out)
    payload = json.loads(out.getvalue())
    assert "systemMessage" in payload
    assert "plan step" in payload["systemMessage"]
    # watermark advanced -> second call is silent
    out2 = io.StringIO()
    payloads.stop_reminder({"cwd": str(tmp_path)}, out=out2)
    assert out2.getvalue() == "{}"


def test_reminder_refires_after_more_progress(tmp_path):
    init_project(tmp_path)
    write_module(tmp_path, "plan.py", _plan_with_completed(3))
    payloads.stop_reminder({"cwd": str(tmp_path)}, out=io.StringIO())  # fires, watermark=3
    write_module(tmp_path, "plan.py", _plan_with_completed(6, n_total=8))
    out = io.StringIO()
    payloads.stop_reminder({"cwd": str(tmp_path)}, out=out)
    assert "systemMessage" in json.loads(out.getvalue())


def test_reminder_installer_adds_stop(tmp_path):
    writes = installers.plan_install(tmp_path, "claude", reminders=True)
    data = writes[0]["data"]
    assert "Stop" in data["hooks"]
    cmds = [h["command"] for e in data["hooks"]["Stop"] for h in e["hooks"]]
    assert "stato hook stop-reminder" in cmds


def test_reminder_off_by_default(tmp_path):
    writes = installers.plan_install(tmp_path, "claude", reminders=False)
    assert "Stop" not in writes[0]["data"].get("hooks", {})
