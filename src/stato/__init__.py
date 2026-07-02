"""Stato: Capture, validate, and transfer AI agent expertise."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("stato")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0.dev0"

from stato.core.bundle import BundleParseResult, parse_bundle
from stato.core.compiler import compile_from_markdown, decompile, validate
from stato.core.composer import (
    graft,
    import_snapshot,
    inspect_archive,
    slice_modules,
    snapshot,
)
from stato.core.converter import ConvertResult, SourceFormat, convert_file
from stato.core.merger import MergeResult, MergeStrategy, merge_archives
from stato.core.module import Diagnostic, ModuleType, ValidationResult
from stato.core.registry import RegistryPackage, fetch_registry_index, search_registry
from stato.core.resume import generate_resume
from stato.core.state_manager import StateManager, init_project, rollback, write_module

__all__ = [
    "__version__",
    "BundleParseResult",
    "parse_bundle",
    "compile_from_markdown",
    "decompile",
    "validate",
    "graft",
    "import_snapshot",
    "inspect_archive",
    "slice_modules",
    "snapshot",
    "ConvertResult",
    "SourceFormat",
    "convert_file",
    "MergeResult",
    "MergeStrategy",
    "merge_archives",
    "Diagnostic",
    "ModuleType",
    "ValidationResult",
    "RegistryPackage",
    "fetch_registry_index",
    "search_registry",
    "generate_resume",
    "StateManager",
    "init_project",
    "rollback",
    "write_module",
]
