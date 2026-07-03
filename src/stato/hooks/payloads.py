"""Hook-side logic — reads host hook JSON on stdin, emits the response.

Exposed via hidden CLI commands `stato hook pre-compact` and
`stato hook session-start`. Kept dependency-free and defensive: a hook must
never crash the host session, so everything is wrapped and failures degrade
to a no-op.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SUMMARY_SHAPING_INSTRUCTIONS = (
    "This project uses stato for durable agent state (.stato/). When you "
    "summarize, preserve VERBATIM where possible: the current phase, decisions "
    "and their rationale, concrete parameter values, error history, and lessons "
    "learned. These facts will be reconciled against validated on-disk state "
    "(.stato/) after compaction — keep them precise rather than paraphrased."
)


def _read_stdin_json() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError, OSError):
        return {}


def _find_project_dir(hook_input: dict) -> Path:
    cwd = hook_input.get("cwd")
    return Path(cwd) if cwd else Path.cwd()


def pre_compact(hook_input: dict | None = None, out=None) -> int:
    """Emit summary-shaping additionalContext; optionally gate on staleness.

    Returns an exit code: 0 (proceed) or 2 (block, freshness gate only).
    """
    out = out or sys.stdout
    if hook_input is None:
        hook_input = _read_stdin_json()
    project_dir = _find_project_dir(hook_input)

    # Freshness gate (opt-in): block auto-compaction when state is stale.
    trigger = hook_input.get("trigger") or hook_input.get("matcher")
    try:
        from stato.core.config import load_config

        gate = load_config(project_dir).hooks_freshness_gate
    except Exception:
        gate = False

    if gate and trigger == "auto":
        transcript = hook_input.get("transcript_path")
        if _state_is_stale(project_dir, transcript):
            print(
                "stato: on-disk state (.stato/) looks stale relative to this "
                "session. Ask the agent to update .stato/ modules (or run "
                "crystallize), then compact.",
                file=sys.stderr,
            )
            return 2

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreCompact",
            "additionalContext": SUMMARY_SHAPING_INSTRUCTIONS,
        }
    }
    out.write(json.dumps(payload))
    return 0


def session_start(hook_input: dict | None = None, out=None) -> int:
    """Emit `stato resume --brief` as additionalContext for the fresh context."""
    out = out or sys.stdout
    if hook_input is None:
        hook_input = _read_stdin_json()
    project_dir = _find_project_dir(hook_input)
    stato_dir = project_dir / ".stato"

    if not stato_dir.exists():
        out.write("{}")
        return 0

    try:
        from stato.core.resume import generate_resume

        recap = generate_resume(stato_dir, brief=True)
    except Exception:
        out.write("{}")
        return 0

    if not recap.strip():
        out.write("{}")
        return 0

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "Restored stato project state (validated, on-disk):\n" + recap
            ),
        }
    }
    out.write(json.dumps(payload))
    return 0


def stop_reminder(hook_input: dict | None = None, out=None) -> int:
    """Nudge to crystallize when plan steps have advanced since the last update.

    Non-blocking. Emits a systemMessage when the number of completed plan steps
    has grown by at least [hooks] reminder_threshold since the last reminder,
    then advances a watermark so it won't re-fire until another threshold lands.
    """
    import json as _json

    out = out or sys.stdout
    if hook_input is None:
        hook_input = _read_stdin_json()
    project_dir = _find_project_dir(hook_input)
    stato_dir = project_dir / ".stato"
    plan_file = stato_dir / "plan.py"

    if not plan_file.exists():
        out.write("{}")
        return 0

    completed = _completed_step_count(plan_file)
    if completed == 0:
        out.write("{}")
        return 0

    try:
        from stato.core.config import load_config

        cfg = load_config(project_dir)
        threshold = getattr(cfg, "hooks_reminder_threshold", 3)
        min_interval = getattr(cfg, "hooks_reminder_min_interval", 0)
    except Exception:
        threshold, min_interval = 3, 0

    watermark_file = stato_dir / ".reminder_state.json"
    watermark, last_fired = 0, None
    if watermark_file.exists():
        try:
            data = _json.loads(watermark_file.read_text())
            watermark = int(data.get("completed", 0))
            last_fired = data.get("last_fired")
        except (ValueError, OSError):
            watermark = 0

    # Rate gate: don't re-fire within min_interval minutes even if steps accrue.
    if min_interval and last_fired and not _interval_elapsed(last_fired, min_interval):
        out.write("{}")
        return 0

    if completed - watermark >= threshold:
        from datetime import datetime, timezone
        try:
            watermark_file.write_text(_json.dumps({
                "completed": completed,
                "last_fired": datetime.now(timezone.utc).isoformat(),
            }))
        except OSError:
            pass
        out.write(_json.dumps({
            "systemMessage": (
                f"stato: {completed - watermark} plan step(s) completed since your "
                "last checkpoint. Consider updating .stato/ (crystallize / update "
                "memory.py) so progress persists."
            )
        }))
        return 0

    out.write("{}")
    return 0


def _interval_elapsed(last_fired_iso: str, min_interval_minutes: int) -> bool:
    """True if at least min_interval minutes have passed since last_fired."""
    from datetime import datetime, timezone
    try:
        last = datetime.fromisoformat(last_fired_iso)
    except (ValueError, TypeError):
        return True
    now = datetime.now(timezone.utc)
    return (now - last).total_seconds() >= min_interval_minutes * 60


def _completed_step_count(plan_file: Path) -> int:
    from stato.core.astload import load_class

    cls = load_class(plan_file.read_text())
    steps = getattr(cls, "steps", None) if cls else None
    if not isinstance(steps, list):
        return 0
    return sum(1 for s in steps if isinstance(s, dict) and s.get("status") == "complete")


def _state_is_stale(project_dir: Path, transcript_path: str | None,
                     threshold_seconds: int = 900) -> bool:
    """True if the transcript is meaningfully newer than .stato/memory.py."""
    memory = project_dir / ".stato" / "memory.py"
    if not memory.exists():
        return False  # nothing to be stale
    if not transcript_path:
        return False
    tpath = Path(transcript_path)
    if not tpath.exists():
        return False
    try:
        return tpath.stat().st_mtime - memory.stat().st_mtime > threshold_seconds
    except OSError:
        return False
