"""Claude Code bridge — generates CLAUDE.md.

Since v0.6 all bridges share the engine in stato.bridge.engine; this module
remains as a back-compat shim for code importing ClaudeCodeBridge or
generate_bridge directly.
"""
from __future__ import annotations

from pathlib import Path

from stato.bridge.base import BridgeBase
from stato.bridge.engine import build_bridge_body, write_bridge
from stato.bridge.platforms import BUILTIN_PLATFORMS


class ClaudeCodeBridge(BridgeBase):
    spec = BUILTIN_PLATFORMS["claude"]

    def output_filename(self) -> str:
        return self.spec.output_path

    def generate(self) -> str:
        return build_bridge_body(self.stato_dir, self.spec)

    def write(self, force: bool = False) -> tuple[Path, str]:
        return write_bridge(self.project_dir, self.spec, force=force)


def generate_bridge(project_dir: Path, platform: str = "claude", force: bool = False) -> tuple[Path, str]:
    """Convenience function to generate and write the Claude Code bridge."""
    return ClaudeCodeBridge(project_dir).write(force=force)
