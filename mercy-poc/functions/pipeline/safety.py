"""Safety checks for user input and LLM output.

Provides keyword-based and pattern-matching safety filters. In production,
these would be backed by ML classifiers (e.g., Perspective API, OpenAI
Moderation, or a custom model).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SAFETY_ENABLED = os.getenv("SAFETY_CHECK_ENABLED", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class SafetyResult:
    """Outcome of a safety check."""

    is_safe: bool
    flags: list[str] = field(default_factory=list)
    filtered_text: str = ""


# ---------------------------------------------------------------------------
# Patterns & keyword lists
# ---------------------------------------------------------------------------

_HARMFUL_KEYWORDS: list[str] = [
    "kill myself",
    "suicide",
    "self-harm",
    "hurt myself",
    "end my life",
    "want to die",
]

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
]

_MEDICAL_ADVICE_PHRASES: list[str] = [
    "you should take",
    "i recommend you take",
    "stop taking your medication",
    "increase your dosage",
    "decrease your dosage",
    "you don't need a doctor",
    "skip your appointment",
]

_DISCLAIMER = (
    "Please note: I'm an AI assistant and cannot provide medical advice. "
    "Always consult a qualified healthcare professional for medical decisions."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_harmful_content(text: str) -> list[str]:
    """Return flags for any harmful-content keywords found."""
    lower = text.lower()
    return [kw for kw in _HARMFUL_KEYWORDS if kw in lower]


def _check_pii(text: str) -> list[str]:
    """Return flags for PII patterns detected."""
    return [name for name, pat in _PII_PATTERNS if pat.search(text)]


def _redact_pii(text: str) -> str:
    """Replace detected PII with redaction placeholders."""
    redacted = text
    for name, pat in _PII_PATTERNS:
        redacted = pat.sub(f"[REDACTED_{name.upper()}]", redacted)
    return redacted


def _check_medical_advice(text: str) -> list[str]:
    """Return flags if the text appears to give direct medical advice."""
    lower = text.lower()
    return [phrase for phrase in _MEDICAL_ADVICE_PHRASES if phrase in lower]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_input_safety(text: str) -> SafetyResult:
    """Check user input for harmful content and PII.

    Args:
        text: Raw user input text.

    Returns:
        SafetyResult indicating whether the input is safe to process.
    """
    if not SAFETY_ENABLED:
        return SafetyResult(is_safe=True, flags=[], filtered_text=text)

    flags: list[str] = []

    harmful = _check_harmful_content(text)
    if harmful:
        flags.extend(f"harmful:{kw}" for kw in harmful)
        logger.warning("Harmful content detected in user input: %s", harmful)

    pii = _check_pii(text)
    if pii:
        flags.extend(f"pii:{p}" for p in pii)
        logger.warning("PII detected in user input: %s", pii)

    filtered = _redact_pii(text) if pii else text

    is_safe = len(harmful) == 0
    return SafetyResult(is_safe=is_safe, flags=flags, filtered_text=filtered)


def check_output_safety(text: str) -> SafetyResult:
    """Check LLM output for harmful content and unsupported medical advice.

    If direct medical advice is detected, a disclaimer is appended.

    Args:
        text: LLM-generated response text.

    Returns:
        SafetyResult indicating whether the output is safe to relay.
    """
    if not SAFETY_ENABLED:
        return SafetyResult(is_safe=True, flags=[], filtered_text=text)

    flags: list[str] = []

    harmful = _check_harmful_content(text)
    if harmful:
        flags.extend(f"harmful:{kw}" for kw in harmful)
        logger.warning("Harmful content detected in LLM output: %s", harmful)

    medical = _check_medical_advice(text)
    if medical:
        flags.extend(f"medical_advice:{phrase}" for phrase in medical)
        logger.warning("Unqualified medical advice in LLM output: %s", medical)

    pii = _check_pii(text)
    if pii:
        flags.extend(f"pii_leak:{p}" for p in pii)
        logger.warning("PII leak detected in LLM output: %s", pii)

    filtered = _redact_pii(text) if pii else text

    if medical:
        filtered = f"{filtered}\n\n{_DISCLAIMER}"

    is_safe = len(harmful) == 0
    return SafetyResult(is_safe=is_safe, flags=flags, filtered_text=filtered)
