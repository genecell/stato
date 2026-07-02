"""Privacy scanner — detects sensitive content before export."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PrivacyFinding:
    """A detected sensitive item."""
    file: str
    line: int
    category: str
    description: str
    matched_text: str
    replacement: str


# Ordered by severity / specificity. Each entry:
# (id, pattern, category, description, replacement). The id lets config
# disable specific patterns (e.g. [privacy] disable = ["email"]).
SENSITIVE_PATTERNS = [
    ('anthropic_key', r'sk-ant-[a-zA-Z0-9\-]{20,}', 'api_key', 'Anthropic API key', '{ANTHROPIC_API_KEY}'),
    ('api_key', r'sk-[a-zA-Z0-9]{20,}', 'api_key', 'API key (OpenAI/Anthropic)', '{API_KEY}'),
    ('aws_key', r'AKIA[0-9A-Z]{16}', 'credential', 'AWS access key ID', '{AWS_ACCESS_KEY}'),
    ('github_pat', r'ghp_[a-zA-Z0-9]{36}', 'token', 'GitHub personal access token', '{GITHUB_TOKEN}'),
    ('github_oauth', r'gho_[a-zA-Z0-9]{36}', 'token', 'GitHub OAuth token', '{GITHUB_OAUTH_TOKEN}'),
    ('gitlab_pat', r'glpat-[a-zA-Z0-9\-]{20,}', 'token', 'GitLab personal access token', '{GITLAB_TOKEN}'),
    ('slack_token', r'xox[bpras]-[a-zA-Z0-9\-]{10,}', 'token', 'Slack token', '{SLACK_TOKEN}'),
    ('bearer', r'Bearer\s+[a-zA-Z0-9\-._~+/]{20,}=*', 'token', 'Bearer token', 'Bearer {TOKEN}'),
    ('authorization', r'Authorization:\s*\S+', 'token', 'Authorization header', 'Authorization: {REDACTED}'),
    ('private_key', r'-----BEGIN\s+(RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE KEY-----', 'credential', 'Private key', '{PRIVATE_KEY}'),
    ('db_url', r'(postgres|postgresql|mysql|mongodb|redis)://\S+:\S+@\S+', 'credential', 'Database connection string', '{DATABASE_URL}'),
    ('password', r'(?i)(password|passwd|pwd|secret)\s*[=:]\s*["\']?[^\s"\']{4,}', 'credential', 'Hardcoded password/secret', '{REDACTED_SECRET}'),
    ('home_linux', r'/home/[a-zA-Z0-9_\-]+/', 'path', 'Home directory path (contains username)', '/home/{user}/'),
    ('home_macos', r'/Users/[a-zA-Z0-9_\-]+/', 'path', 'macOS home directory (contains username)', '/Users/{user}/'),
    ('home_windows', r'C:\\\\Users\\\\[a-zA-Z0-9_\\-]+\\\\', 'path', 'Windows home directory (contains username)', 'C:\\\\Users\\\\{user}\\\\'),
    ('internal_ip_10', r'(?<!\d)(10\.\d{1,3}\.\d{1,3}\.\d{1,3})(?!\d)', 'network', 'Internal IP address (10.x.x.x)', '{INTERNAL_IP}'),
    ('internal_ip_192', r'(?<!\d)(192\.168\.\d{1,3}\.\d{1,3})(?!\d)', 'network', 'Internal IP address (192.168.x.x)', '{INTERNAL_IP}'),
    ('email', r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', 'pii', 'Email address', '{EMAIL}'),
]

# Bioinformatics-specific patterns
BIO_PATTERNS = [
    ('subject_id', r'(?i)(patient|subject|donor)[_\-]?[iI][dD]\s*[=:]\s*\S+', 'pii', 'Patient/subject identifier', '{SUBJECT_ID}'),
    ('mrn', r'(?i)MRN\s*[=:]\s*\d+', 'pii', 'Medical record number', 'MRN: {REDACTED}'),
    ('ssn', r'\b\d{3}-\d{2}-\d{4}\b', 'pii', 'Possible SSN pattern', '{SSN}'),
]


class PrivacyScanner:
    """Scans module content for sensitive information."""

    def __init__(self, extra_patterns=None, ignore_file=None, disable=None):
        disable = set(disable or [])
        # Drop the id column; skip any pattern whose id is disabled.
        self.patterns = [
            p[1:] for p in (SENSITIVE_PATTERNS + BIO_PATTERNS)
            if p[0] not in disable
        ]
        if extra_patterns:
            for ep in extra_patterns:
                if isinstance(ep, dict):
                    self.patterns.append((
                        ep["pattern"], ep.get("category", "custom"),
                        ep.get("description", "Custom pattern"),
                        ep.get("replacement", "{REDACTED}"),
                    ))
                else:
                    self.patterns.append(tuple(ep))
        self.ignore_patterns = self._load_ignore_file(ignore_file)

    @classmethod
    def from_config(cls, project_dir, ignore_file=None):
        """Build a scanner honoring [privacy] disable / extra_patterns."""
        from stato.core.config import load_config

        cfg = load_config(project_dir)
        return cls(
            extra_patterns=cfg.privacy_extra_patterns,
            ignore_file=ignore_file,
            disable=cfg.privacy_disable,
        )

    def _load_ignore_file(self, path: Path | None) -> list[str]:
        """Load .statoignore patterns."""
        if path is None or not path.exists():
            return []
        return [
            line.strip() for line in path.read_text().splitlines()
            if line.strip() and not line.startswith('#')
        ]

    def scan_file(self, filepath: str, content: str) -> list[PrivacyFinding]:
        """Scan a single file for sensitive content."""
        findings = []
        for i, line in enumerate(content.splitlines(), 1):
            for pattern, category, description, replacement in self.patterns:
                for match in re.finditer(pattern, line):
                    matched = match.group(0)
                    display = matched[:20] + '...' if len(matched) > 20 else matched
                    findings.append(PrivacyFinding(
                        file=filepath,
                        line=i,
                        category=category,
                        description=description,
                        matched_text=display,
                        replacement=replacement,
                    ))
        return findings

    def scan_directory(self, stato_dir: Path) -> list[PrivacyFinding]:
        """Scan all modules in .stato/ directory."""
        findings = []
        for py_file in sorted(stato_dir.rglob('*.py')):
            if '.history' in py_file.parts or '__pycache__' in py_file.parts:
                continue
            relative = py_file.relative_to(stato_dir)
            content = py_file.read_text()
            findings.extend(self.scan_file(str(relative), content))
        return findings

    def sanitize(self, content: str) -> str:
        """Replace detected secrets with placeholders."""
        result = content
        for pattern, _category, _description, replacement in self.patterns:
            result = re.sub(pattern, replacement, result)
        return result
