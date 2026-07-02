"""Bridge plugins — custom platform specs from the user config directory.

A plugin is a .py file in <user config dir>/bridges/ defining a
PLATFORM_SPEC dict, e.g.:

    PLATFORM_SPEC = {
        "key": "zed",
        "output_path": ".rules",
        "title": "# Project Rules",
    }

Plugins are user-authored local code loaded via importlib and are only
read when [plugins] enabled = true in the stato config. This is the one
deliberate code-loading point in stato — opt-in, and never applied to
module/archive content.
"""
from __future__ import annotations

import importlib.util

from stato.bridge.engine import PlatformSpec

_SPEC_KEYS = {"key", "output_path", "title", "rules_header", "rules", "frontmatter", "description"}


def load_plugin_platforms() -> dict[str, PlatformSpec]:
    """Load PlatformSpecs from config-dir plugins. Empty unless enabled."""
    from stato.core.config import load_config, user_config_dir

    if not load_config(None).plugins_enabled:
        return {}

    bridges_dir = user_config_dir() / "bridges"
    if not bridges_dir.is_dir():
        return {}

    platforms: dict[str, PlatformSpec] = {}
    for plugin_file in sorted(bridges_dir.glob("*.py")):
        try:
            mod_spec = importlib.util.spec_from_file_location(
                f"stato_bridge_plugin_{plugin_file.stem}", plugin_file
            )
            module = importlib.util.module_from_spec(mod_spec)
            mod_spec.loader.exec_module(module)
        except Exception as e:  # a broken plugin must not break the CLI
            import sys

            print(
                f"stato: skipping bridge plugin {plugin_file.name}: {e}",
                file=sys.stderr,
            )
            continue

        raw = getattr(module, "PLATFORM_SPEC", None)
        if not isinstance(raw, dict) or "key" not in raw or "output_path" not in raw:
            continue
        kwargs = {k: v for k, v in raw.items() if k in _SPEC_KEYS}
        spec = PlatformSpec(**kwargs)
        platforms[spec.key] = spec

    return platforms
