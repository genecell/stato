"""Built-in bridge platform specs.

AGENTS.md ("agents") is the primary bridge — it is the Linux Foundation
cross-tool standard read by Codex, Cursor, Copilot, Zed, Devin, Gemini CLI
and ~two dozen more. Platform-specific files exist for tools that give
their own file higher precedence or don't read AGENTS.md.
"""
from __future__ import annotations

from stato.bridge.engine import PlatformSpec

CURSOR_MDC_FRONTMATTER = """---
description: Stato expertise index — validated agent state in .stato/
alwaysApply: true
---"""

BUILTIN_PLATFORMS: dict[str, PlatformSpec] = {
    "agents": PlatformSpec(
        key="agents",
        output_path="AGENTS.md",
        description="AGENTS.md — cross-tool standard (Codex, Cursor, Copilot, Zed, ...)",
    ),
    "claude": PlatformSpec(
        key="claude",
        output_path="CLAUDE.md",
        description="CLAUDE.md — Claude Code",
    ),
    "cursor": PlatformSpec(
        key="cursor",
        output_path=".cursor/rules/stato.mdc",
        frontmatter=CURSOR_MDC_FRONTMATTER,
        title="# Project Rules",
        rules_header="## Rules",
        description=".cursor/rules/stato.mdc — Cursor (modern rules format)",
    ),
    "copilot": PlatformSpec(
        key="copilot",
        output_path=".github/copilot-instructions.md",
        description=".github/copilot-instructions.md — GitHub Copilot",
    ),
    "gemini": PlatformSpec(
        key="gemini",
        output_path="GEMINI.md",
        description="GEMINI.md — Gemini CLI",
    ),
    "generic": PlatformSpec(
        key="generic",
        output_path="README.stato.md",
        description="README.stato.md — any other tool or human readers",
    ),
    # Legacy formats, kept for compatibility
    "cursor-legacy": PlatformSpec(
        key="cursor-legacy",
        output_path=".cursorrules",
        title="# Project Rules",
        rules_header="## Rules",
        description=".cursorrules — deprecated Cursor format",
    ),
}

# 'codex' historically generated AGENTS.md; it is now an alias for 'agents'.
PLATFORM_ALIASES = {"codex": "agents"}


def resolve_platform(name: str) -> PlatformSpec | None:
    """Resolve a platform name or alias to its spec (plugins included)."""
    name = PLATFORM_ALIASES.get(name, name)
    if name in BUILTIN_PLATFORMS:
        return BUILTIN_PLATFORMS[name]

    from stato.bridge.plugins import load_plugin_platforms

    return load_plugin_platforms().get(name)


def all_platform_names(include_legacy: bool = False) -> list[str]:
    names = [
        k for k in BUILTIN_PLATFORMS
        if include_legacy or not k.endswith("-legacy")
    ]
    from stato.bridge.plugins import load_plugin_platforms

    names.extend(load_plugin_platforms().keys())
    return names
