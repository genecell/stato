"""Stato: Capture, validate, and transfer AI agent expertise."""

__version__ = "0.5.0"

from stato.core.compiler import validate, decompile, compile_from_markdown
from stato.core.module import ModuleType, Diagnostic, ValidationResult
from stato.core.state_manager import StateManager, init_project, write_module, rollback
from stato.core.composer import (
    snapshot,
    import_snapshot,
    inspect_archive,
    slice_modules,
    graft,
)
from stato.core.bundle import BundleParseResult, parse_bundle
from stato.core.resume import generate_resume
from stato.core.converter import convert_file, ConvertResult, SourceFormat
from stato.core.merger import merge_archives, MergeResult, MergeStrategy
from stato.core.registry import search_registry, RegistryPackage, fetch_registry_index
