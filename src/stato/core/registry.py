"""Registry — search and install shared expertise packages."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

# Default registry URL — override via [registry] url in config or STATO_REGISTRY_URL
DEFAULT_REGISTRY = "https://raw.githubusercontent.com/genecell/stato/master/docs/registry/index.toml"


@dataclass
class RegistryPackage:
    """A package in the registry."""
    name: str
    description: str
    author: str
    url: str
    version: str
    tags: list[str]
    modules: int
    updated: str
    sha256: str = ""  # optional "sha256:<hex>" of the .stato archive file


def fetch_registry_index(registry_url: str = DEFAULT_REGISTRY) -> list[RegistryPackage]:
    """Fetch and parse the registry index.

    Uses urllib (no extra dependencies) to fetch the TOML index.
    """
    import urllib.request

    import tomli

    try:
        with urllib.request.urlopen(registry_url, timeout=10) as response:
            content = response.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"Could not fetch registry: {e}") from e

    try:
        data = tomli.loads(content)
    except tomli.TOMLDecodeError as e:
        raise RuntimeError(
            f"Registry index at {registry_url} is not valid TOML: {e}"
        ) from e

    packages_table = data.get("packages", {})
    if not isinstance(packages_table, dict):
        raise RuntimeError(
            f"Registry index at {registry_url} has an unexpected schema: "
            "'packages' should be a table of package entries"
        )

    packages = []
    for name, info in packages_table.items():
        packages.append(RegistryPackage(
            name=name,
            description=info.get("description", ""),
            author=info.get("author", "unknown"),
            url=info.get("url", ""),
            version=info.get("version", "0.0.0"),
            tags=info.get("tags", []),
            modules=info.get("modules", 0),
            updated=info.get("updated", ""),
            sha256=info.get("sha256", ""),
        ))

    return packages


def search_registry(query: str, packages: list[RegistryPackage]) -> list[RegistryPackage]:
    """Search packages by name, description, and tags."""
    from stato.core.search import score_text

    results = []
    for pkg in packages:
        score = (
            3 * score_text(query, pkg.name)
            + 2 * score_text(query, pkg.description)
            + sum(score_text(query, tag) for tag in pkg.tags)
        )
        if score > 0:
            results.append((score, pkg))

    results.sort(key=lambda x: x[0], reverse=True)
    return [pkg for _, pkg in results]


def file_sha256(path: Path) -> str:
    """Compute "sha256:<hex>" of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def download_package(pkg: RegistryPackage, output_dir: Path) -> Path:
    """Download a package archive; verify sha256 when the index declares one."""
    import urllib.request

    output_path = output_dir / f"{pkg.name}.stato"

    try:
        urllib.request.urlretrieve(pkg.url, str(output_path))
    except Exception as e:
        raise RuntimeError(f"Could not download {pkg.name}: {e}") from e

    if pkg.sha256:
        actual = file_sha256(output_path)
        if actual != pkg.sha256:
            output_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Downloaded archive for {pkg.name} failed checksum verification "
                f"(expected {pkg.sha256}, got {actual}). Refusing to install."
            )

    return output_path


def make_index_entry(archive_path: Path, url: str = "", author: str = "") -> str:
    """Generate a ready-to-PR index.toml entry for a .stato archive."""
    from datetime import date

    from stato.core.composer import inspect_archive

    info = inspect_archive(archive_path)
    name = info["name"] or archive_path.stem
    lines = [
        f"[packages.{name}]",
        f'description = "{info["description"]}"',
        f'author = "{author or "unknown"}"',
        f'url = "{url or "https://example.com/path/to/" + archive_path.name}"',
        'version = "1.0.0"',
        "tags = []",
        f"modules = {len(info['modules'])}",
        f'updated = "{date.today().isoformat()}"',
        f'sha256 = "{file_sha256(archive_path)}"',
    ]
    return "\n".join(lines) + "\n"
