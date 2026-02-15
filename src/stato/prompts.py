"""Prompt templates for stato workflows."""


def get_crystallize_prompt() -> str:
    """Return the crystallize prompt template."""
    return CRYSTALLIZE_PROMPT


CRYSTALLIZE_PROMPT = """\
# Stato Crystallize Prompt

## Instructions

You are capturing expertise for this project using stato. Read these \
instructions and write structured modules to `.stato/`.

**If you have session-specific knowledge** (you've been working on this \
project, learned parameters, made decisions, hit failures): Capture that \
expertise in the modules below. This is the primary and richest mode.

**If this is a fresh session** (you just started and have no session \
history): Read the project's existing code, configs, notebooks, and \
documentation. Infer expertise from what you can observe. Write modules \
based on what the codebase reveals. This is less rich than session capture \
but still valuable.

Either way, write the following modules:

## Step 1: Initialize
```
pip install stato  # if not already installed
stato init
```
(Safe to run if already initialized, won't overwrite existing modules)

## Step 2: Create SKILL modules
For each significant task or technique you've used in this project,
create a skill module in .stato/skills/<name>.py:

```python
class SkillName:
    \"\"\"Brief description of what this skill does.\"\"\"
    name = "skill_name"
    version = "1.0.0"
    depends_on = ["packages_you_used"]
    default_params = {
        "param": value,  # why this value
    }
    lessons_learned = \"\"\"
    - What worked and why
    - What didn't work and why
    - Edge cases and gotchas
    - Parameter values refined through experimentation
    \"\"\"
    @staticmethod
    def run(**kwargs):
        pass
```

Write one skill per major capability. Use descriptive filenames.

## Step 3: Create PLAN module
Write .stato/plan.py reflecting your analysis/development pipeline:

```python
class ProjectPlan:
    name = "project_name"
    objective = "what this project aims to accomplish"
    steps = [
        {"id": 1, "action": "step_name", "status": "complete",
         "output": "what was produced"},
        {"id": 2, "action": "next_step", "status": "pending"},
    ]
    decision_log = \"\"\"
    Key decisions and rationale.
    \"\"\"
```

## Step 4: Create MEMORY module
Write .stato/memory.py:

```python
class ProjectState:
    phase = "current_phase"
    tasks = ["remaining", "tasks"]
    known_issues = {"issue": "description"}
    reflection = \"\"\"
    Where the project stands and what to do next.
    \"\"\"
```

## Step 5: Create CONTEXT module
Write .stato/context.py:

```python
class ProjectContext:
    project = "project_name"
    description = "what this project is"
    datasets = ["paths/to/data"]
    environment = {"package": "version"}
    conventions = ["coding conventions used"]
```

## Step 6: Validate
```
stato validate .stato/
```
Fix any errors reported.

## Step 7: Generate bridge
```
stato bridge --platform claude
```

Done. Your expertise is now captured in portable, validated modules.
To share: `stato snapshot --name "my-expert" --template`
"""


def get_web_crystallize_prompt() -> str:
    """Return the web AI crystallize prompt template."""
    return WEB_CRYSTALLIZE_PROMPT


WEB_CRYSTALLIZE_PROMPT = """\
Crystallize our conversation into a stato bundle file.

Output a single Python file called `stato_bundle.py` that I can save and import
into a coding agent. Use this exact format:

```python
# stato_bundle.py -- Crystallized from web AI conversation
# Import with: stato import-bundle stato_bundle.py

SKILLS = {
    "skill_name": \'\'\'
class SkillName:
    \"\"\"Brief description.\"\"\"
    name = "skill_name"
    version = "1.0.0"
    depends_on = ["packages_used"]
    default_params = {
        "param": value,  # why this value
    }
    lessons_learned = \"\"\"
    - What worked and why
    - What didn't and why
    - Edge cases and gotchas
    \"\"\"
    @staticmethod
    def run(**kwargs): pass
\'\'\',
}

PLAN = \'\'\'
class ProjectPlan:
    name = "project_name"
    objective = "what we're trying to accomplish"
    steps = [
        {"id": 1, "action": "step_name", "status": "complete", "output": "what was produced"},
        {"id": 2, "action": "next_step", "status": "pending"},
    ]
    decision_log = \"\"\"
    Key decisions made during our conversation.
    \"\"\"
\'\'\'

MEMORY = \'\'\'
class ProjectState:
    phase = "current_phase"
    tasks = ["remaining", "tasks"]
    known_issues = {"issue": "description"}
    reflection = \"\"\"
    Summary of where things stand.
    \"\"\"
\'\'\'

CONTEXT = \'\'\'
class ProjectContext:
    project = "project_name"
    description = "what this project is"
    datasets = ["relevant_data"]
    environment = {"package": "version"}
    conventions = ["conventions established in conversation"]
\'\'\'
```

Rules:
- Create one skill per major topic/technique we discussed
- Include specific parameters, thresholds, and values from our conversation
- lessons_learned should capture the WHY, not just the WHAT
- Plan steps should reflect our actual discussion progression
- Be thorough, this is the only bridge between this conversation and a coding agent

Output the complete bundle file now."""

# FUTURE (v1.0): Auto-crystallize mode
# The coding agent runs stato crystallize itself during the session.
# Agent detects it should crystallize (end of session, before compact)
# and writes modules without human intervention.
# Requires agent-side integration (hooks, triggers, or CLAUDE.md instructions
# that tell the agent to periodically crystallize).
