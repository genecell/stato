"""Codex bridge — generates AGENTS.md.

'codex' is now an alias for the 'agents' platform: AGENTS.md is the
cross-tool standard, not a Codex-specific file. Back-compat shim.
"""
from __future__ import annotations

from pathlib import Path

from stato.bridge.base import BridgeBase
from stato.bridge.engine import build_bridge_body, write_bridge
from stato.bridge.platforms import BUILTIN_PLATFORMS


class CodexBridge(BridgeBase):
    spec = BUILTIN_PLATFORMS["agents"]

    def output_filename(self) -> str:
        return self.spec.output_path

    def generate(self) -> str:
        return build_bridge_body(self.stato_dir, self.spec)

    def write(self, force: bool = False) -> tuple[Path, str]:
        return write_bridge(self.project_dir, self.spec, force=force)


def generate_bridge(project_dir: Path, platform: str = "codex", force: bool = False) -> tuple[Path, str]:
    """Convenience function to generate and write the AGENTS.md bridge."""
    return CodexBridge(project_dir).write(force=force)
