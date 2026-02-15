"""State manager — validate-gated read/write with file-based backup."""
from __future__ import annotations

import difflib
from datetime import datetime, timezone
from pathlib import Path

from stato.core.compiler import validate
from stato.core.module import ValidationResult


def init_project(project_dir: Path) -> Path:
    """Initialize a stato project directory structure.

    Creates .stato/ with skills/, .history/, and prompts/ subdirectories.
    Writes the crystallize prompt template to prompts/crystallize.md.
    Returns project_dir for chaining.
    """
    as_dir = project_dir / ".stato"
    as_dir.mkdir(parents=True, exist_ok=True)
    (as_dir / "skills").mkdir(exist_ok=True)
    (as_dir / ".history").mkdir(exist_ok=True)
    (as_dir / "prompts").mkdir(exist_ok=True)

    # Always write latest crystallize prompts (tool-owned, not user data)
    from stato.prompts import CRYSTALLIZE_PROMPT, WEB_CRYSTALLIZE_PROMPT
    (as_dir / "prompts" / "crystallize.md").write_text(CRYSTALLIZE_PROMPT)
    (as_dir / "prompts" / "crystallize_web.md").write_text(WEB_CRYSTALLIZE_PROMPT)

    # Create .statoignore template if it doesn't exist
    statoignore = project_dir / ".statoignore"
    if not statoignore.exists():
        statoignore.write_text(
            "# .statoignore — patterns to suppress in privacy scan\n"
            "# One pattern per line, supports * wildcards\n"
            "# Lines starting with # are comments\n"
        )

    return project_dir


class StateManager:
    def __init__(self, project_dir: Path, backend: str = "auto"):
        self.project_dir = project_dir
        self.stato_dir = project_dir / ".stato"
        self.history_dir = self.stato_dir / ".history"

        if backend == "auto":
            self.backend = "file"
        else:
            self.backend = backend

    def write(self, rel_path: str, source: str) -> ValidationResult:
        """Validate → backup → write if valid. Returns ValidationResult."""
        result = validate(source)
        if not result.success:
            return result

        target = self.stato_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)

        # Backup existing file
        if target.exists() and self.backend != "none":
            self._backup(rel_path, target)

        # Write corrected source if auto-corrections were applied
        write_source = result.corrected_source or source
        target.write_text(write_source)

        return result

    def read(self, rel_path: str) -> str:
        """Read module source from .stato/rel_path."""
        target = self.stato_dir / rel_path
        return target.read_text()

    def history(self, rel_path: str, n: int = 10) -> list[dict]:
        """Return backup entries for the module, newest first."""
        stem = Path(rel_path).stem
        backups = sorted(
            self.history_dir.glob(f"{stem}.*.py"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [
            {"timestamp": self._extract_timestamp(p), "path": p}
            for p in backups[:n]
        ]

    def diff(self, rel_path: str, against: str = "previous") -> str:
        """Return unified diff between current and previous version."""
        current = self.read(rel_path)
        hist = self.history(rel_path, n=1)
        if not hist:
            return ""
        previous = hist[0]["path"].read_text()
        diff_lines = difflib.unified_diff(
            previous.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile=f"{rel_path} (previous)",
            tofile=f"{rel_path} (current)",
        )
        return "".join(diff_lines)

    def rollback(self, rel_path: str, to: str = "previous") -> bool:
        """Restore a previous version. Backs up current first."""
        hist = self.history(rel_path, n=1)
        if not hist:
            return False
        target = self.stato_dir / rel_path
        if target.exists():
            self._backup(rel_path, target)
        previous_content = hist[0]["path"].read_text()
        target.write_text(previous_content)
        return True

    def _backup(self, rel_path: str, target: Path) -> None:
        """Copy current file to .history/ with timestamp."""
        self.history_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(rel_path).stem
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        backup_path = self.history_dir / f"{stem}.{ts}.py"
        backup_path.write_text(target.read_text())

    @staticmethod
    def _extract_timestamp(path: Path) -> str:
        """Extract timestamp from backup filename like qc.20260213T120000123456.py."""
        parts = path.stem.split(".", 1)
        return parts[1] if len(parts) > 1 else ""


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def write_module(project_dir: Path, rel_path: str, source: str) -> ValidationResult:
    """Convenience: create StateManager and write."""
    sm = StateManager(project_dir)
    return sm.write(rel_path, source)


def rollback(project_dir: Path, rel_path: str, to: str = "previous") -> bool:
    """Convenience: create StateManager and rollback."""
    sm = StateManager(project_dir)
    return sm.rollback(rel_path, to)
