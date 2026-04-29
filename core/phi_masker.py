from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Compiled redaction patterns — ordered from most specific to least specific
# so a wider pattern doesn't swallow a narrower one's match group.
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # SSN  123-45-6789
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    # Date of birth  DOB: 01/02/1980  or  dob=1980-01-02
    (re.compile(r"\bDOB[:\s=]+\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b", re.IGNORECASE), "[DOB]"),
    # MRN / patient-id patterns  MRN-000001  PAT-12345  PATID:00001
    (re.compile(r"\b(?:MRN|PAT(?:ID)?|PATIENT[-_]?ID)[-:\s]?\d+\b", re.IGNORECASE), "[MRN]"),
    # NPI  NPI: 1234567890 (10-digit)
    (re.compile(r"\bNPI[-:\s]?\d{10}\b", re.IGNORECASE), "[NPI]"),
    # Phone  (555) 123-4567  555-123-4567  +15551234567
    (re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"), "[PHONE]"),
    # Email address
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    # IPv4  192.168.1.1
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
    # Bearer / access tokens  Bearer eyJ…  access_token=abc123
    (
        re.compile(
            r"(?:Bearer\s+|access_token[=:\s]+|Authorization[=:\s]+)[A-Za-z0-9\-._~+/=]{16,}",
            re.IGNORECASE,
        ),
        "[TOKEN]",
    ),
    # Generic secret/password/api-key assignments  secret=abc  password: "xyz"
    (
        re.compile(
            r"(?:secret|password|passwd|api[_-]?key|client[_-]?secret|token)"
            r"[=:\s\"']+[^\s\"',;]{6,}",
            re.IGNORECASE,
        ),
        "[SECRET]",
    ),
    # JWT  three base64url segments separated by dots
    (re.compile(r"\beyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\b"), "[JWT]"),
]


def mask_phi(text: str) -> str:
    """Return *text* with PHI, PII, and secrets replaced by placeholder tokens.

    Safe to call on empty strings or non-string values (returns unchanged).
    """
    if not isinstance(text, str) or not text:
        return text
    for pattern, placeholder in _PATTERNS:
        text = pattern.sub(placeholder, text)
    return text


def mask_dict(data: dict[str, str]) -> dict[str, str]:
    """Apply mask_phi to every string value in *data*, returning a new dict."""
    return {k: mask_phi(v) if isinstance(v, str) else v for k, v in data.items()}
