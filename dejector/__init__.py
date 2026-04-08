"""
DEJECTOR — Prompt injection detection for emails, documents, and AI agent skills.

Usage:
    from dejector import DejectorScanner

    scanner = DejectorScanner(profile="email")
    verdict = scanner.scan_text("Some text to check...")
    if not verdict.safe:
        print(f"INJECTION DETECTED: {verdict.confidence:.3f}")

Profiles:
    - email:    Strict scanning for emails (threshold 0.70, ensemble)
    - skill:    Relaxed scanning for OpenClaw skills (threshold 0.95, ensemble)
    - document: Standard scanning for documents (threshold 0.70, ensemble)
    - fast:     Single-model fast scan (threshold 0.70)
"""

from dejector.core import (
    DejectorScanner,
    ScanResult,
    ScanVerdict,
    PROFILES,
    PRIMARY_MODEL,
    SECONDARY_MODEL,
)

__version__ = "0.1.0"
__all__ = [
    "DejectorScanner",
    "ScanResult",
    "ScanVerdict",
    "PROFILES",
]
