"""Converter — import expertise from CLAUDE.md, .cursorrules, AGENTS.md, SKILL.md."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SourceFormat(Enum):
    CLAUDE = "claude"
    CURSOR = "cursor"
    CODEX = "codex"
    SKILLKIT = "skillkit"
    GENERIC = "generic"


@dataclass
class ConvertResult:
    """Result of converting an external file to stato modules."""
    skills: dict[str, str] = field(default_factory=dict)
    context: str | None = None
    plan: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_format: SourceFormat = SourceFormat.GENERIC


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format(filepath: Path) -> SourceFormat:
    """Detect the source format from filename and content."""
    name = filepath.name.lower()

    if name == "claude.md":
        return SourceFormat.CLAUDE
    elif name == ".cursorrules":
        return SourceFormat.CURSOR
    elif name == "agents.md":
        return SourceFormat.CODEX
    elif name == "skill.md":
        return SourceFormat.SKILLKIT

    # Content-based detection
    content = filepath.read_text()
    lines = content.split("\n")
    has_steps = any(l.strip().startswith("## Steps") for l in lines)
    has_rules = any(l.strip().startswith("## Rules") for l in lines)
    if has_steps or has_rules:
        if lines and lines[0].strip().startswith("# "):
            return SourceFormat.SKILLKIT

    return SourceFormat.GENERIC


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def convert_file(filepath: Path, format: SourceFormat | None = None) -> ConvertResult:
    """Convert an external file to stato module sources."""
    if format is None:
        format = detect_format(filepath)

    content = filepath.read_text()

    if format == SourceFormat.CLAUDE:
        return convert_claude_md(content)
    elif format == SourceFormat.CURSOR:
        return convert_cursorrules(content)
    elif format == SourceFormat.CODEX:
        return convert_agents_md(content)
    elif format == SourceFormat.SKILLKIT:
        return convert_skillkit(content)
    else:
        return convert_generic(content)


# ---------------------------------------------------------------------------
# CLAUDE.md parser
# ---------------------------------------------------------------------------

def convert_claude_md(content: str) -> ConvertResult:
    """Convert a CLAUDE.md file to stato modules."""
    sections = split_markdown_sections(content)
    skills: dict[str, str] = {}
    conventions: list[str] = []
    environment: dict = {}
    warnings: list[str] = []

    for heading, body in sections:
        if heading is None:
            conventions.extend(extract_conventions(body))
            environment.update(extract_environment(body))
        else:
            skill_name = slugify(heading)
            params = extract_params(body)
            lessons = extract_lessons(body)
            deps = extract_dependencies(body)

            if params or lessons or deps:
                skills[skill_name] = generate_skill_source(
                    name=skill_name,
                    description=heading,
                    depends_on=deps,
                    default_params=params,
                    lessons_learned=lessons,
                )
            else:
                conventions.extend(extract_conventions(body))
                if not body.strip():
                    warnings.append(f"Section '{heading}' was empty, skipped")

    context_source = generate_context_source(
        project=extract_project_name(content),
        description="Converted from CLAUDE.md",
        environment=environment,
        conventions=conventions,
    )

    return ConvertResult(
        skills=skills,
        context=context_source,
        plan=None,
        warnings=warnings,
        source_format=SourceFormat.CLAUDE,
    )


# ---------------------------------------------------------------------------
# .cursorrules parser
# ---------------------------------------------------------------------------

def convert_cursorrules(content: str) -> ConvertResult:
    """Convert a .cursorrules file to stato modules."""
    lines = content.strip().split("\n")
    has_headings = any(line.startswith("##") for line in lines)

    if has_headings:
        result = convert_claude_md(content)
        result.source_format = SourceFormat.CURSOR
        return result
    else:
        conventions = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                conventions.append(line)

        context_source = generate_context_source(
            project="converted_project",
            description="Converted from .cursorrules",
            environment={},
            conventions=conventions,
        )

        return ConvertResult(
            skills={},
            context=context_source,
            plan=None,
            warnings=["Plain rules file: all content added as conventions. "
                       "Consider splitting into skills manually for better organization."],
            source_format=SourceFormat.CURSOR,
        )


# ---------------------------------------------------------------------------
# AGENTS.md parser
# ---------------------------------------------------------------------------

def convert_agents_md(content: str) -> ConvertResult:
    """Convert an AGENTS.md (Codex) file to stato modules."""
    result = convert_claude_md(content)
    result.source_format = SourceFormat.CODEX
    return result


# ---------------------------------------------------------------------------
# SKILL.md (SkillKit) parser
# ---------------------------------------------------------------------------

def convert_skillkit(content: str) -> ConvertResult:
    """Convert a SkillKit SKILL.md file to a stato skill module."""
    sections = split_markdown_sections(content)

    skill_name = "unnamed_skill"
    description = ""
    steps: list[str] = []
    rules: list[str] = []

    for heading, body in sections:
        if heading is None:
            first_line = content.strip().split("\n")[0]
            if first_line.startswith("# "):
                skill_name = slugify(first_line[2:].strip())
                description = body.strip().split("\n")[0] if body.strip() else first_line[2:].strip()
            else:
                description = body.strip().split("\n")[0] if body.strip() else ""
        elif heading.lower() == "steps":
            for line in body.split("\n"):
                line = line.strip()
                step = re.sub(r'^\d+[\.)\]]\s*', '', line)
                if step:
                    steps.append(step)
        elif heading.lower() == "rules":
            for line in body.split("\n"):
                line = line.strip()
                rule = re.sub(r'^[-*\u2022]\s+', '', line)
                if rule:
                    rules.append(rule)

    lessons_parts = []
    if rules:
        for r in rules:
            lessons_parts.append(f"- {r}")
    if steps:
        lessons_parts.append("- Process steps: " + " -> ".join(steps))

    lessons = "\n".join(lessons_parts)

    skill_source = generate_skill_source(
        name=skill_name,
        description=description,
        depends_on=[],
        default_params={},
        lessons_learned=lessons,
    )

    warnings = []
    if not rules and not steps:
        warnings.append("No ## Steps or ## Rules found. Skill may be sparse.")

    return ConvertResult(
        skills={skill_name: skill_source},
        context=None,
        plan=None,
        warnings=warnings,
        source_format=SourceFormat.SKILLKIT,
    )


# ---------------------------------------------------------------------------
# Generic markdown parser
# ---------------------------------------------------------------------------

def convert_generic(content: str) -> ConvertResult:
    """Convert generic markdown/text to stato modules."""
    result = convert_claude_md(content)
    result.source_format = SourceFormat.GENERIC
    if not result.skills and not result.context:
        result.context = generate_context_source(
            project="converted_project",
            description="Converted from generic file",
            environment={},
            conventions=[line.strip() for line in content.split("\n")
                         if line.strip() and not line.startswith("#")],
        )
        result.warnings.append("Could not extract structured skills. "
                               "All content added as context conventions.")
    return result


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def split_markdown_sections(content: str) -> list[tuple[str | None, str]]:
    """Split markdown into (heading, body) pairs."""
    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    current_body: list[str] = []

    for line in content.split("\n"):
        match = re.match(r'^##\s+(.+)$', line)
        if match:
            if current_heading is not None or current_body:
                sections.append((current_heading, "\n".join(current_body)))
            current_heading = match.group(1).strip()
            current_body = []
        else:
            if re.match(r'^#\s+', line) and current_heading is None and not current_body:
                continue
            current_body.append(line)

    if current_heading is not None or current_body:
        sections.append((current_heading, "\n".join(current_body)))

    return sections


def extract_conventions(text: str) -> list[str]:
    """Extract convention-like statements from text."""
    conventions = []

    for line in text.split("\n"):
        line = line.strip()
        cleaned = re.sub(r'^[-*\u2022]\s+', '', line)

        if not cleaned:
            continue

        patterns = [
            r'^(Always|Never|Use|Prefer|Avoid|Do not|Don\'t)\b',
            r'\b(should|must|shall)\b',
        ]

        for pattern in patterns:
            if re.search(pattern, cleaned, re.IGNORECASE):
                conventions.append(cleaned)
                break

    return conventions


def extract_params(text: str) -> dict:
    """Extract parameter-like assignments from text."""
    params: dict = {}

    for match in re.finditer(
        r'(\w+)\s*[=:]\s*(\d+(?:\.\d+)?|"[^"]*"|\'[^\']*\'|True|False)', text
    ):
        key = match.group(1)
        value = match.group(2)
        try:
            if value in ('True', 'False'):
                params[key] = value == 'True'
            elif '.' in value:
                params[key] = float(value)
            elif value.startswith('"') or value.startswith("'"):
                params[key] = value.strip("\"'")
            else:
                params[key] = int(value)
        except ValueError:
            params[key] = value

    return params


def extract_dependencies(text: str) -> list[str]:
    """Extract package/library dependencies mentioned in text."""
    deps: set[str] = set()

    known_packages = {
        'sqlalchemy', 'fastapi', 'pydantic', 'pytest', 'numpy', 'pandas',
        'scanpy', 'scipy', 'sklearn', 'torch', 'tensorflow', 'flask',
        'django', 'celery', 'redis', 'alembic', 'docker', 'kubernetes',
        'react', 'vue', 'angular', 'express', 'nextjs',
    }

    text_lower = text.lower()
    for pkg in known_packages:
        if pkg in text_lower:
            deps.add(pkg)

    return sorted(deps)


def extract_environment(text: str) -> dict:
    """Extract environment/version info from text."""
    env: dict = {}

    py_match = re.search(r'[Pp]ython\s+(\d+\.\d+(?:\.\d+)?)', text)
    if py_match:
        env["python"] = py_match.group(1)

    node_match = re.search(r'[Nn]ode(?:\.?js)?\s+(\d+(?:\.\d+)?)', text)
    if node_match:
        env["node"] = node_match.group(1)

    return env


def extract_lessons(text: str) -> str:
    """Extract lessons/tips/notes from text as a markdown string."""
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith(("-", "*", "\u2022")) or len(line) > 20:
            cleaned = re.sub(r'^[-*\u2022]\s+', '- ', line)
            if not cleaned.startswith("- "):
                cleaned = f"- {cleaned}"
            lines.append(cleaned)

    return "\n".join(lines) if lines else ""


def extract_project_name(content: str) -> str:
    """Try to extract project name from content."""
    match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if match:
        name = match.group(1).strip()
        for prefix in ["Project:", "Project", "CLAUDE.md for"]:
            if name.lower().startswith(prefix.lower()):
                name = name[len(prefix):].strip()
        return slugify(name) if name else "converted_project"
    return "converted_project"


def slugify(text: str) -> str:
    """Convert text to a valid Python identifier / filename."""
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', text.lower()).strip('_')
    if slug and slug[0].isdigit():
        slug = f"skill_{slug}"
    return slug or "unnamed"


# ---------------------------------------------------------------------------
# Source generators
# ---------------------------------------------------------------------------

def generate_skill_source(name: str, description: str, depends_on: list,
                          default_params: dict, lessons_learned: str) -> str:
    """Generate a stato skill module source string."""
    class_name = ''.join(word.capitalize() for word in name.split('_'))
    if not class_name:
        class_name = "UnnamedSkill"

    deps_str = repr(depends_on)
    params_str = repr(default_params)

    lessons_escaped = lessons_learned.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')

    return f'''class {class_name}:
    """Converted from external file: {description}"""
    name = "{name}"
    version = "1.0.0"
    depends_on = {deps_str}
    default_params = {params_str}
    lessons_learned = """
{lessons_escaped}
    """
    @staticmethod
    def run(**kwargs): pass
'''


def generate_context_source(project: str, description: str,
                            environment: dict, conventions: list) -> str:
    """Generate a stato context module source string."""
    class_name = ''.join(word.capitalize() for word in project.split('_'))
    if not class_name:
        class_name = "Unnamed"

    env_str = repr(environment)
    conv_str = repr(conventions)

    return f'''class {class_name}Context:
    project = "{project}"
    description = "{description}"
    environment = {env_str}
    conventions = {conv_str}
'''


# ---------------------------------------------------------------------------
# Smart convert prompt
# ---------------------------------------------------------------------------

def generate_smart_convert_prompt(content: str, filename: str) -> str:
    """Generate a prompt for AI-assisted conversion."""
    return f'''I have an existing file called `{filename}` that I want to convert into stato modules.
Here is its content:

```
{content}
```

Please convert this into a stato bundle file. Output a single Python file called `stato_bundle.py` using this format:

```python
# stato_bundle.py — Converted from {filename}
# Import with: stato import-bundle stato_bundle.py

SKILLS = {{
    "skill_name": \'\'\'
class SkillName:
    """Brief description."""
    name = "skill_name"
    version = "1.0.0"
    depends_on = ["packages_used"]
    default_params = {{
        "param": value,
    }}
    lessons_learned = """
    - What this skill captures
    """
    @staticmethod
    def run(**kwargs): pass
\'\'\',
}}

CONTEXT = \'\'\'
class ProjectContext:
    project = "project_name"
    description = "description"
    environment = {{"package": "version"}}
    conventions = ["conventions from the file"]
\'\'\'
```

Rules:
- Create one skill per major topic/section
- Extract specific parameters, thresholds, and values
- lessons_learned should capture rules and best practices
- conventions should capture general project-wide rules
- Be thorough but don't invent information not in the original file

Output the complete bundle file now.'''
