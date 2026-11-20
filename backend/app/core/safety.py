"""Privacy and integrity checks applied to every incoming memory candidate.

* **Secrets** (API keys, passwords, private keys, card numbers) are never stored.
* **PII** (emails, phone numbers) is redacted before storage.
* **Prompt-injection / poisoning** patterns (instructions aimed at the agent,
  attempts to override rules, exfiltration requests) are detected so the
  decision engine can discard or quarantine the input.

Rules are deterministic regular expressions so every decision is explainable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("api_key", re.compile(r"\b(sk|pk|rk|ghp|gho|xox[abpr])[-_][A-Za-z0-9_\-]{12,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("password", re.compile(r"\b(password|passwd|pwd|passcode|pin)\s*(is|=|:)\s*\S+", re.I)),
    ("card_number", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("bearer_token", re.compile(r"\bbearer\s+[A-Za-z0-9\-_\.=]{16,}", re.I)),
]

PII_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    ("phone", re.compile(r"(?<!\d)(\+?\d{1,3}[ -]?)?(\(?\d{3}\)?[ -]?)\d{3}[ -]?\d{4}(?!\d)"), "[REDACTED_PHONE]"),
]

INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("override_instructions", re.compile(r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|all|earlier|system)\b.{0,20}\b(instructions?|rules?|prompts?|memor(y|ies))", re.I)),
    ("role_hijack", re.compile(r"\b(you are now|act as|pretend to be|from now on you)\b", re.I)),
    ("system_prompt", re.compile(r"\b(system prompt|developer message|jailbreak)\b", re.I)),
    ("exfiltration", re.compile(r"\b(send|email|post|upload|leak|exfiltrate)\b.{0,40}\b(password|credentials?|secrets?|api keys?|tokens?|all (the )?memor(y|ies))\b", re.I)),
    ("dangerous_command", re.compile(r"(rm\s+-rf\s+/|del\s+/[sq]|format\s+c:|drop\s+table|;\s*shutdown|curl\s+[^|]+\|\s*(sh|bash))", re.I)),
    ("always_instruction", re.compile(r"\b(always|never)\b.{0,40}\b(approve|grant|transfer|pay|reveal|disable|bypass)\b", re.I)),
    ("markup_injection", re.compile(r"<\s*(script|iframe|system|instruction)[^>]*>", re.I)),
]

UNVERIFIABLE_CLAIM = re.compile(
    r"\b(guaranteed|100% (true|certain)|everyone knows|secretly|confirmed by insiders|trust me)\b", re.I
)


@dataclass
class SafetyReport:
    secrets: list[str] = field(default_factory=list)
    pii: list[str] = field(default_factory=list)
    injection: list[str] = field(default_factory=list)
    unverifiable: bool = False
    redacted_text: str = ""

    @property
    def privacy_risk(self) -> float:
        if self.secrets:
            return 1.0
        return min(1.0, 0.35 * len(self.pii))

    @property
    def injection_risk(self) -> float:
        return min(1.0, 0.6 * len(self.injection))


def scan(text: str) -> SafetyReport:
    rep = SafetyReport(redacted_text=text)
    for name, pat in SECRET_PATTERNS:
        if pat.search(text):
            rep.secrets.append(name)
    red = text
    for name, pat, repl in PII_PATTERNS:
        if pat.search(red):
            rep.pii.append(name)
            red = pat.sub(repl, red)
    for name, pat in SECRET_PATTERNS:
        red = pat.sub("[REDACTED_SECRET]", red)
    rep.redacted_text = red
    for name, pat in INJECTION_PATTERNS:
        if pat.search(text):
            rep.injection.append(name)
    rep.unverifiable = bool(UNVERIFIABLE_CLAIM.search(text))
    return rep


def redact(text: str) -> str:
    return scan(text).redacted_text


def escape_for_context(text: str) -> str:
    """Neutralise characters that could break out of a memory data block."""
    return (
        text.replace("<", "‹").replace(">", "›").replace("```", "ʼʼʼ").replace("\n", " ")
    )
