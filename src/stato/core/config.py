"""Stato configuration — layered TOML config with env-var overrides.

Precedence (lowest to highest):
    built-in defaults
    user config    ($XDG_CONFIG_HOME/stato/config.toml, default ~/.config/stato/)
    project config (.stato/config.toml)
    environment    (STATO_REGISTRY_URL, ...)

CLI flags override everything at the call site.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/genecell/stato/master/docs/registry/index.toml"
)

CONFIG_TEMPLATE = """\
# Stato configuration. All sections and keys are optional.
# Precedence: defaults < user config < project config < env vars < CLI flags.

[registry]
# url = "https://example.com/my-registry/index.toml"   # or env STATO_REGISTRY_URL

[privacy]
# disable = ["email", "internal_ip_10"]   # pattern ids to turn off (see `stato config`)
# extra_patterns = [
#   { pattern = 'LAB-[0-9]{6}', category = "pii", description = "Lab sample id", replacement = "{SAMPLE_ID}" },
# ]

[bridge]
# default = "agents"                # platform used when --platform is omitted
# platforms = ["agents", "claude"]  # what `stato bridge --platform all` generates

[validate]
# strict = false            # treat warnings/advice as errors
# suppress = ["I006"]       # diagnostic codes to hide

[history]
# keep = 50                 # backups retained per module in .stato/.history/

[hooks]
# freshness_gate = false      # PreCompact blocks auto-compaction when state is stale
# reminder_threshold = 3      # Stop-hook nudge after N completed plan steps

[plugins]
# enabled = false           # load custom bridges from <user config dir>/bridges/*.py
"""


@dataclass
class StatoConfig:
    registry_url: str = DEFAULT_REGISTRY_URL
    privacy_disable: list[str] = field(default_factory=list)
    privacy_extra_patterns: list[dict] = field(default_factory=list)
    bridge_default: str = "agents"
    bridge_platforms: list[str] = field(default_factory=lambda: ["agents", "claude"])
    validate_strict: bool = False
    validate_suppress: list[str] = field(default_factory=list)
    history_keep: int = 50
    hooks_freshness_gate: bool = False
    hooks_reminder_threshold: int = 3
    plugins_enabled: bool = False
    # provenance: key -> "default" | "user" | "project" | "env"
    sources: dict = field(default_factory=dict)


def user_config_dir() -> Path:
    """Resolve the stato user config directory (XDG-aware, env-overridable)."""
    override = os.environ.get("STATO_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "stato"


def user_config_path() -> Path:
    return user_config_dir() / "config.toml"


def project_config_path(project_dir: Path) -> Path:
    return project_dir / ".stato" / "config.toml"


def _read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    import tomli

    try:
        return tomli.loads(path.read_text())
    except (tomli.TOMLDecodeError, OSError) as e:
        raise RuntimeError(f"Could not parse config {path}: {e}") from e


# (config_attr, toml_section, toml_key, coerce)
_KEYS = [
    ("registry_url", "registry", "url", str),
    ("privacy_disable", "privacy", "disable", list),
    ("privacy_extra_patterns", "privacy", "extra_patterns", list),
    ("bridge_default", "bridge", "default", str),
    ("bridge_platforms", "bridge", "platforms", list),
    ("validate_strict", "validate", "strict", bool),
    ("validate_suppress", "validate", "suppress", list),
    ("history_keep", "history", "keep", int),
    ("hooks_freshness_gate", "hooks", "freshness_gate", bool),
    ("hooks_reminder_threshold", "hooks", "reminder_threshold", int),
    ("plugins_enabled", "plugins", "enabled", bool),
]

_ENV_VARS = {
    "registry_url": "STATO_REGISTRY_URL",
}


def _apply_layer(cfg: StatoConfig, data: dict, layer_name: str) -> None:
    for attr, section, key, coerce in _KEYS:
        if section in data and key in data[section]:
            value = data[section][key]
            if not isinstance(value, coerce):
                raise RuntimeError(
                    f"Config [{section}] {key}: expected {coerce.__name__}, "
                    f"got {type(value).__name__}"
                )
            setattr(cfg, attr, value)
            cfg.sources[attr] = layer_name


def load_config(project_dir: Path | None = None) -> StatoConfig:
    """Load the effective configuration for a project directory."""
    cfg = StatoConfig()
    cfg.sources = {attr: "default" for attr, *_ in _KEYS}

    _apply_layer(cfg, _read_toml(user_config_path()), "user")
    if project_dir is not None:
        _apply_layer(cfg, _read_toml(project_config_path(Path(project_dir))), "project")

    for attr, env_name in _ENV_VARS.items():
        value = os.environ.get(env_name)
        if value:
            setattr(cfg, attr, value)
            cfg.sources[attr] = f"env:{env_name}"

    return cfg


def write_config_template(path: Path) -> bool:
    """Write the commented config template if absent. Returns True if written."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CONFIG_TEMPLATE)
    return True
