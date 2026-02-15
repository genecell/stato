"""Registry — search and install shared expertise packages."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Default registry URL
DEFAULT_REGISTRY = "https://raw.githubusercontent.com/genecell/stato-registry/main/index.toml"


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
        raise RuntimeError(f"Could not fetch registry: {e}")

    data = tomli.loads(content)
    packages = []

    for name, info in data.get("packages", {}).items():
        packages.append(RegistryPackage(
            name=name,
            description=info.get("description", ""),
            author=info.get("author", "unknown"),
            url=info.get("url", ""),
            version=info.get("version", "0.0.0"),
            tags=info.get("tags", []),
            modules=info.get("modules", 0),
            updated=info.get("updated", ""),
        ))

    return packages


def search_registry(query: str, packages: list[RegistryPackage]) -> list[RegistryPackage]:
    """Search packages by name, description, and tags."""
    query_lower = query.lower()
    results = []

    for pkg in packages:
        score = 0
        if query_lower in pkg.name.lower():
            score += 3
        if query_lower in pkg.description.lower():
            score += 2
        if any(query_lower in tag.lower() for tag in pkg.tags):
            score += 1

        if score > 0:
            results.append((score, pkg))

    results.sort(key=lambda x: x[0], reverse=True)
    return [pkg for _, pkg in results]


def download_package(pkg: RegistryPackage, output_dir: Path) -> Path:
    """Download a package archive."""
    import urllib.request

    output_path = output_dir / f"{pkg.name}.stato"

    try:
        urllib.request.urlretrieve(pkg.url, str(output_path))
    except Exception as e:
        raise RuntimeError(f"Could not download {pkg.name}: {e}")

    return output_path
