"""Generic bridge — generates README.stato.md. Back-compat shim."""
from __future__ import annotations

from pathlib import Path

from stato.bridge.base import BridgeBase
from stato.bridge.engine import build_bridge_body, write_bridge
from stato.bridge.platforms import BUILTIN_PLATFORMS


class GenericBridge(BridgeBase):
    spec = BUILTIN_PLATFORMS["generic"]

    def output_filename(self) -> str:
        return self.spec.output_path

    def generate(self) -> str:
        return build_bridge_body(self.stato_dir, self.spec)

    def write(self, force: bool = False) -> tuple[Path, str]:
        return write_bridge(self.project_dir, self.spec, force=force)


def generate_bridge(project_dir: Path, platform: str = "generic", force: bool = False) -> tuple[Path, str]:
    """Convenience function to generate and write the generic bridge."""
    return GenericBridge(project_dir).write(force=force)
