"""Generic bridge — generates README.stato.md."""
from __future__ import annotations

from pathlib import Path

from stato.bridge.base import BridgeBase
from stato.core.composer import _discover_modules
from stato.core.module import ModuleType
from stato.modules.plan import PlanHelpers


class GenericBridge(BridgeBase):
    def output_filename(self) -> str:
        return "README.stato.md"

    def generate(self) -> str:
        modules = _discover_modules(self.stato_dir)
        plans = [m for m in modules if m["module_type"] == ModuleType.PLAN]

        lines = [
            "# Stato Project",
            "",
            "This project uses Stato for structured expertise management.",
            "Agent state modules live in `.stato/` as validated Python files.",
            "",
            "## Modules",
            "",
        ]

        for mod in modules:
            cls = mod["namespace"].get(mod["class_name"])
            name = getattr(cls, "name", mod["class_name"])
            lines.append(
                f"- **{name}** ({mod['module_type'].value}) "
                f"— `.stato/{mod['rel_path']}`"
            )

        lines.append("")

        for p in plans:
            cls = p["namespace"].get(p["class_name"])
            if cls and hasattr(cls, "steps"):
                done, total = PlanHelpers.progress(cls.steps)
                lines.append(
                    f"## Plan: {getattr(cls, 'name', '?')}"
                )
                lines.append(f"Progress: {done}/{total} complete.")
                lines.append(
                    f"See `.stato/{p['rel_path']}` for details."
                )
                lines.append("")

        lines.extend([
            "## Usage",
            "```bash",
            "pip install stato",
            "stato validate .stato/",
            "stato status",
            "```",
        ])

        return "\n".join(lines) + "\n"


def generate_bridge(project_dir: Path, platform: str = "generic", force: bool = False) -> tuple[Path, str]:
    """Convenience function to generate and write the generic bridge."""
    bridge = GenericBridge(project_dir)
    return bridge.write(force=force)
