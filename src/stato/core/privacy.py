"""Privacy scanner — detects sensitive content before export."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PrivacyFinding:
    """A detected sensitive item."""
    file: str
    line: int
    category: str
    description: str
    matched_text: str
    replacement: str


# Ordered by severity / specificity
SENSITIVE_PATTERNS = [
    # API keys and tokens
    (r'sk-ant-[a-zA-Z0-9\-]{20,}', 'api_key', 'Anthropic API key', '{ANTHROPIC_API_KEY}'),
    (r'sk-[a-zA-Z0-9]{20,}', 'api_key', 'API key (OpenAI/Anthropic)', '{API_KEY}'),
    (r'AKIA[0-9A-Z]{16}', 'credential', 'AWS access key ID', '{AWS_ACCESS_KEY}'),
    (r'ghp_[a-zA-Z0-9]{36}', 'token', 'GitHub personal access token', '{GITHUB_TOKEN}'),
    (r'gho_[a-zA-Z0-9]{36}', 'token', 'GitHub OAuth token', '{GITHUB_OAUTH_TOKEN}'),
    (r'glpat-[a-zA-Z0-9\-]{20,}', 'token', 'GitLab personal access token', '{GITLAB_TOKEN}'),
    (r'xox[bpras]-[a-zA-Z0-9\-]{10,}', 'token', 'Slack token', '{SLACK_TOKEN}'),

    # Bearer / Authorization headers
    (r'Bearer\s+[a-zA-Z0-9\-._~+/]{20,}=*', 'token', 'Bearer token', 'Bearer {TOKEN}'),
    (r'Authorization:\s*\S+', 'token', 'Authorization header', 'Authorization: {REDACTED}'),

    # Private keys
    (r'-----BEGIN\s+(RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE KEY-----', 'credential', 'Private key', '{PRIVATE_KEY}'),

    # Database connection strings
    (r'(postgres|postgresql|mysql|mongodb|redis)://\S+:\S+@\S+', 'credential', 'Database connection string', '{DATABASE_URL}'),

    # Passwords in assignments
    (r'(?i)(password|passwd|pwd|secret)\s*[=:]\s*["\']?[^\s"\']{4,}', 'credential', 'Hardcoded password/secret', '{REDACTED_SECRET}'),

    # Home directory paths (leaks username)
    (r'/home/[a-zA-Z0-9_\-]+/', 'path', 'Home directory path (contains username)', '/home/{user}/'),
    (r'/Users/[a-zA-Z0-9_\-]+/', 'path', 'macOS home directory (contains username)', '/Users/{user}/'),
    (r'C:\\\\Users\\\\[a-zA-Z0-9_\\-]+\\\\', 'path', 'Windows home directory (contains username)', 'C:\\\\Users\\\\{user}\\\\'),

    # IP addresses (internal networks)
    (r'(?<!\d)(10\.\d{1,3}\.\d{1,3}\.\d{1,3})(?!\d)', 'network', 'Internal IP address (10.x.x.x)', '{INTERNAL_IP}'),
    (r'(?<!\d)(192\.168\.\d{1,3}\.\d{1,3})(?!\d)', 'network', 'Internal IP address (192.168.x.x)', '{INTERNAL_IP}'),

    # Email addresses
    (r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', 'pii', 'Email address', '{EMAIL}'),
]

# Bioinformatics-specific patterns
BIO_PATTERNS = [
    (r'(?i)(patient|subject|donor)[_\-]?[iI][dD]\s*[=:]\s*\S+', 'pii', 'Patient/subject identifier', '{SUBJECT_ID}'),
    (r'(?i)MRN\s*[=:]\s*\d+', 'pii', 'Medical record number', 'MRN: {REDACTED}'),
    (r'\b\d{3}-\d{2}-\d{4}\b', 'pii', 'Possible SSN pattern', '{SSN}'),
]


class PrivacyScanner:
    """Scans module content for sensitive information."""

    def __init__(self, extra_patterns=None, ignore_file=None):
        self.patterns = SENSITIVE_PATTERNS + BIO_PATTERNS
        if extra_patterns:
            self.patterns.extend(extra_patterns)
        self.ignore_patterns = self._load_ignore_file(ignore_file)

    def _load_ignore_file(self, path: Optional[Path]) -> list[str]:
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
        for pattern, category, description, replacement in self.patterns:
            result = re.sub(pattern, replacement, result)
        return result
