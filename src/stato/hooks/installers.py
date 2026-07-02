"""Per-platform hook installers — merge-not-overwrite, idempotent.

Each installer writes stato's Design A hooks into the platform's native config:
  claude -> .claude/settings.json         (JSON "hooks")
  codex  -> .codex/hooks.json             (JSON, Claude-compatible shape)
  gemini -> .gemini/settings.json "hooks" + a stato extension bundle

Stato-owned entries carry a marker so re-running updates only them and
uninstall removes only them. Doc URLs inline so schema drift is a one-file fix.
"""
from __future__ import annotations

import json
from pathlib import Path

# Marker embedded in every stato-authored hook command so we can find/replace
# only our own entries.
STATO_HOOK_MARKER = "stato hook"

PLATFORM_HOOK_FILES = {
    "claude": ".claude/settings.json",   # code.claude.com/docs/en/hooks
    "codex": ".codex/hooks.json",        # developers.openai.com/codex/hooks
    "gemini": ".gemini/settings.json",   # geminicli.com/docs/hooks/reference
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        text = path.read_text().strip()
        return json.loads(text) if text else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _dump_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _command_hook(cmd: str) -> dict:
    return {"type": "command", "command": cmd}


def _is_stato_entry(entry: dict) -> bool:
    for hook in entry.get("hooks", []):
        if STATO_HOOK_MARKER in hook.get("command", ""):
            return True
    return False


def _merge_event(hooks_obj: dict, event: str, entries: list[dict]) -> None:
    """Replace stato-owned entries for an event, keep everyone else's."""
    existing = [e for e in hooks_obj.get(event, []) if not _is_stato_entry(e)]
    hooks_obj[event] = existing + entries


def _remove_stato(hooks_obj: dict) -> None:
    for event in list(hooks_obj.keys()):
        kept = [e for e in hooks_obj[event] if not _is_stato_entry(e)]
        if kept:
            hooks_obj[event] = kept
        else:
            del hooks_obj[event]


# --- Claude Code -----------------------------------------------------------

def _claude_entries() -> dict:
    return {
        "PreCompact": [
            {"matcher": "manual",
             "hooks": [_command_hook("stato hook pre-compact")]},
            {"matcher": "auto",
             "hooks": [_command_hook("stato hook pre-compact")]},
        ],
        "SessionStart": [
            {"matcher": "compact",
             "hooks": [_command_hook("stato hook session-start")]},
            {"matcher": "startup|resume",
             "hooks": [_command_hook("stato hook session-start")]},
        ],
    }


def _reminder_entry() -> dict:
    return {"Stop": [{"hooks": [_command_hook("stato hook stop-reminder")]}]}


def _install_claude(project_dir: Path, uninstall: bool, reminders: bool = False) -> dict:
    path = project_dir / PLATFORM_HOOK_FILES["claude"]
    settings = _load_json(path)
    hooks = settings.setdefault("hooks", {})
    if uninstall:
        _remove_stato(hooks)
    else:
        entries = dict(_claude_entries())
        if reminders:
            entries.update(_reminder_entry())
        for event, e in entries.items():
            _merge_event(hooks, event, e)
    if not hooks:
        settings.pop("hooks", None)
    return {"path": path, "data": settings}


# --- Codex CLI (Claude-compatible hook shape) ------------------------------

def _install_codex(project_dir: Path, uninstall: bool, reminders: bool = False) -> dict:
    path = project_dir / PLATFORM_HOOK_FILES["codex"]
    config = _load_json(path)
    # Codex hooks.json is a bare hooks object (event -> entries)
    if uninstall:
        _remove_stato(config)
    else:
        # Codex has PostCompact in addition to PreCompact/SessionStart
        entries = dict(_claude_entries())
        entries["PostCompact"] = [
            {"hooks": [_command_hook("stato hook session-start")]},
        ]
        if reminders:
            entries.update(_reminder_entry())
        for event, e in entries.items():
            _merge_event(config, event, e)
    return {"path": path, "data": config}


# --- Gemini CLI (settings.json hooks + extension bundle) -------------------

def _gemini_entries() -> dict:
    # Gemini: PreCompress (advisory) + SessionStart injection; no PostCompress.
    return {
        "PreCompress": [
            {"hooks": [_command_hook("stato hook pre-compact")]},
        ],
        "SessionStart": [
            {"hooks": [_command_hook("stato hook session-start")]},
        ],
    }


def _install_gemini(project_dir: Path, uninstall: bool) -> list[dict]:
    writes = []
    path = project_dir / PLATFORM_HOOK_FILES["gemini"]
    settings = _load_json(path)
    hooks = settings.setdefault("hooks", {})
    if uninstall:
        _remove_stato(hooks)
    else:
        for event, entries in _gemini_entries().items():
            _merge_event(hooks, event, entries)
    if not hooks:
        settings.pop("hooks", None)
    writes.append({"path": path, "data": settings})

    # Extension bundle: MCP server + slash commands
    ext_dir = project_dir / ".gemini" / "extensions" / "stato"
    ext_manifest = ext_dir / "gemini-extension.json"
    if uninstall:
        writes.append({"path": ext_manifest, "delete": True, "dir": ext_dir})
    else:
        writes.append({
            "path": ext_manifest,
            "data": {
                "name": "stato",
                "version": "1.0.0",
                "description": "Stato validated agent state: MCP server + commands",
                "contextFileName": "GEMINI.md",
                "mcpServers": {
                    "stato": {"command": "stato", "args": ["mcp"]}
                },
            },
        })
        writes.append({
            "path": ext_dir / "commands" / "stato" / "save.toml",
            "text": (
                'description = "Crystallize current work into .stato modules"\n'
                'prompt = "Read and follow .stato/prompts/crystallize.md, then '
                'run: stato validate .stato/"\n'
            ),
        })
        writes.append({
            "path": ext_dir / "commands" / "stato" / "resume.toml",
            "text": (
                'description = "Restore project state from .stato"\n'
                'prompt = "Run: stato resume --raw, and use the output as '
                'current project context."\n'
            ),
        })
    return writes


# --- Public API ------------------------------------------------------------

def plan_install(project_dir: Path, platform: str, uninstall: bool = False,
                 reminders: bool = False) -> list[dict]:
    """Return the list of file writes for a platform (without applying them).

    `reminders` adds a Stop-hook nudge (claude/codex only — Gemini's SessionEnd
    exit code is ignored, so a reminder there wouldn't surface).
    """
    if platform == "claude":
        return [_install_claude(project_dir, uninstall, reminders)]
    if platform == "codex":
        return [_install_codex(project_dir, uninstall, reminders)]
    if platform == "gemini":
        return _install_gemini(project_dir, uninstall)
    raise ValueError(f"Unknown hook platform: {platform}")


def apply_writes(writes: list[dict]) -> list[str]:
    """Apply planned writes to disk. Returns human-readable change lines."""
    changed = []
    for w in writes:
        path = w["path"]
        if w.get("delete"):
            if path.exists():
                path.unlink()
                changed.append(f"removed {path}")
            ext_dir = w.get("dir")
            if ext_dir and ext_dir.exists():
                import shutil

                shutil.rmtree(ext_dir, ignore_errors=True)
                changed.append(f"removed {ext_dir}/")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if "text" in w:
            path.write_text(w["text"])
        else:
            _dump_json(path, w["data"])
        changed.append(f"wrote {path}")
    return changed


def status(project_dir: Path) -> dict:
    """Report which platforms currently have stato hooks installed."""
    result = {}
    for platform, rel in PLATFORM_HOOK_FILES.items():
        path = project_dir / rel
        data = _load_json(path)
        hooks = data.get("hooks", data)  # codex is a bare hooks object
        installed = any(
            _is_stato_entry(e)
            for entries in (hooks.values() if isinstance(hooks, dict) else [])
            for e in entries
        )
        result[platform] = installed
    return result
