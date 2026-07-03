"""AST-only module materialization — replaces exec() throughout stato.

Stato modules are declarative: a single class whose fields are literal values.
That means we never need to execute user code to inspect it. This module
parses source with `ast`, evaluates class-body fields with `ast.literal_eval`,
and builds a real class object via `type()` — with method *stubs* that carry
the original annotations — so downstream code (semantic passes, resume, diff,
merge, status) keeps its attribute-access API without any code execution.

Security property: importing/validating/merging an archive from an untrusted
source cannot run its code. Non-literal field values (comprehensions, calls,
names) are skipped and reported, never evaluated.
"""
from __future__ import annotations

import ast
import warnings
from dataclasses import dataclass, field


def safe_parse(source: str) -> ast.Module:
    """ast.parse that suppresses SyntaxWarning (raises SyntaxError as usual).

    A stray `\\d` in a non-raw user docstring makes ast.parse emit a
    SyntaxWarning that would otherwise pollute all CLI output. Every parse of
    user module source should go through here.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(source)


def parse_collecting_warnings(source: str) -> tuple[ast.Module, list[str]]:
    """Parse and return (tree, [SyntaxWarning messages]) for authoring lints."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SyntaxWarning)
        tree = ast.parse(source)
    msgs = [str(w.message) for w in caught if issubclass(w.category, SyntaxWarning)]
    return tree, msgs


@dataclass
class MaterializeResult:
    """Outcome of AST materialization of one module source."""
    namespace: dict | None          # {class_name: cls} or None on parse failure
    class_name: str | None = None
    skipped_fields: list[str] = field(default_factory=list)  # non-literal, not evaluated
    error: str | None = None        # parse/build failure description


def _make_method_stub(node: ast.FunctionDef | ast.AsyncFunctionDef):
    """Build a non-executable stand-in that preserves name and annotations."""

    def _stub(*_args, **_kwargs):
        raise NotImplementedError(
            f"'{node.name}' is a stato AST stub; module methods are never "
            "executed by stato itself"
        )

    annotations: dict[str, str] = {}
    for arg in list(node.args.args) + list(node.args.kwonlyargs):
        if arg.annotation is not None:
            annotations[arg.arg] = ast.unparse(arg.annotation)
    if node.args.vararg is not None and node.args.vararg.annotation is not None:
        annotations[node.args.vararg.arg] = ast.unparse(node.args.vararg.annotation)
    if node.returns is not None:
        annotations["return"] = ast.unparse(node.returns)

    _stub.__name__ = node.name
    _stub.__qualname__ = node.name
    _stub.__doc__ = ast.get_docstring(node)
    _stub.__annotations__ = annotations
    _stub.__stato_stub__ = True
    return _stub


def materialize(source: str, class_node: ast.ClassDef | None = None) -> MaterializeResult:
    """Build a class object from source without executing it.

    If class_node is None, the first class definition in the source is used.
    """
    if class_node is None:
        try:
            tree = safe_parse(source)
        except SyntaxError as e:
            return MaterializeResult(namespace=None, error=f"syntax error: {e.msg}")
        class_node = next(
            (n for n in tree.body if isinstance(n, ast.ClassDef)), None
        )
        if class_node is None:
            return MaterializeResult(namespace=None, error="no class definition found")

    attrs: dict = {}
    skipped: list[str] = []

    docstring = ast.get_docstring(class_node)
    if docstring:
        attrs["__doc__"] = docstring

    for node in class_node.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not targets:
                continue
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                skipped.extend(targets)
                continue
            for name in targets:
                attrs[name] = value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is None:
                continue
            try:
                attrs[node.target.id] = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                skipped.append(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            attrs[node.name] = _make_method_stub(node)

    try:
        cls = type(class_node.name, (), attrs)
    except (TypeError, ValueError) as e:
        return MaterializeResult(
            namespace=None,
            class_name=class_node.name,
            skipped_fields=skipped,
            error=f"could not build class: {e}",
        )

    return MaterializeResult(
        namespace={class_node.name: cls},
        class_name=class_node.name,
        skipped_fields=skipped,
    )


def load_class(source: str):
    """Convenience: return the materialized class or None (lenient loader)."""
    result = materialize(source)
    if result.namespace is None or result.class_name is None:
        return None
    return result.namespace.get(result.class_name)


def extract_field_values(source: str, class_node: ast.ClassDef | None = None) -> dict:
    """Return {field_name: literal value} for a module, without executing it."""
    result = materialize(source, class_node)
    if result.namespace is None or result.class_name is None:
        return {}
    cls = result.namespace[result.class_name]
    return {
        k: v for k, v in vars(cls).items()
        if not k.startswith("__") and not callable(v)
    }
