#!/usr/bin/env python3
"""
DEJECTOR Corpus Test Runner — Scan test corpus and report detection results.

Reads the manifest from generate_test_corpus.py output, scans each file
through DejectorScanner, and produces a detailed report.

Usage:
    python3 test_corpus.py                          # Run with defaults (email profile)
    python3 test_corpus.py --profile email          # Email profile (ensemble, threshold 0.7)
    python3 test_corpus.py --profile document       # Document profile
    python3 test_corpus.py --profile fast           # Single-model fast scan
    python3 test_corpus.py --json                   # JSON output
    python3 test_corpus.py --category direct_injection  # Filter by category
    python3 test_corpus.py --subtlety subtle        # Filter by subtlety level

Exit codes:
    0 = all tests passed
    1 = one or more tests failed
    2 = error (missing corpus, bad args)
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Add venv site-packages to path so we can use torch/transformers
# without requiring a global install or special exec permissions
_venv_site = Path(__file__).parent / "venv" / "lib"
if _venv_site.exists():
    for _p in _venv_site.glob("python*/site-packages"):
        sys.path.insert(0, str(_p))

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

TESTS_DIR = PROJECT_DIR / "tests"
MANIFEST = TESTS_DIR / "corpus-manifest.json"


def load_manifest() -> dict:
    if not MANIFEST.exists():
        print(f"ERROR: Corpus not found at {MANIFEST}", file=sys.stderr)
        print(f"Run: python3 {PROJECT_DIR / 'generate_test_corpus.py'}", file=sys.stderr)
        sys.exit(2)
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def run_tests(
    profile: str = "email",
    threshold: float | None = None,
    ensemble: bool | None = None,
    category_filter: str | None = None,
    subtlety_filter: str | None = None,
    json_output: bool = False,
) -> bool:
    """Run corpus tests. Returns True if all passed."""
    from dejector_core import DejectorScanner, PROFILES

    manifest = load_manifest()
    cases = manifest["cases"]

    # Apply filters
    if category_filter:
        cases = [c for c in cases if c["category"] == category_filter]
    if subtlety_filter:
        cases = [c for c in cases if c["subtlety"] == subtlety_filter]

    if not cases:
        print("No test cases match filters.")
        return True

    # Build scanner kwargs
    kwargs = {"profile": profile}
    if threshold is not None:
        kwargs["threshold"] = threshold
    if ensemble is not None:
        kwargs["ensemble"] = ensemble

    p_desc = PROFILES.get(profile, {})
    print(f"DEJECTOR Corpus Test Runner")
    print(f"{'=' * 70}")
    print(f"Profile:    {profile} — {p_desc.get('description', 'custom')}")
    print(f"Threshold:  {kwargs.get('threshold', p_desc.get('threshold', 0.7))}")
    print(f"Ensemble:   {kwargs.get('ensemble', p_desc.get('ensemble', True))}")
    print(f"Test cases: {len(cases)}")
    if category_filter:
        print(f"Category:   {category_filter}")
    if subtlety_filter:
        print(f"Subtlety:   {subtlety_filter}")
    print(f"{'=' * 70}\n")

    scanner = DejectorScanner(**kwargs)

    results = []
    passed = 0
    failed = 0
    false_positives = []  # legit emails marked as injection
    false_negatives = []  # injections marked as safe

    for i, case in enumerate(cases):
        filepath = TESTS_DIR / case["file"]
        if not filepath.exists():
            print(f"  [{i+1}/{len(cases)}] MISSING: {case['file']}")
            failed += 1
            results.append({**case, "result": "ERROR", "reason": "file not found"})
            continue

        text = filepath.read_text(encoding="utf-8", errors="replace")
        expected = case["expected"]

        t0 = time.time()
        verdict = scanner.scan_text(text, filename=case["file"])
        elapsed_ms = (time.time() - t0) * 1000

        actual = "REJECT" if not verdict.safe else "PASS"
        match = actual == expected

        if match:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"
            if expected == "PASS" and actual == "REJECT":
                false_positives.append(case["file"])
            elif expected == "REJECT" and actual == "PASS":
                false_negatives.append(case["file"])

        icon = "✓" if match else "✗"
        subtlety_tag = f"[{case['subtlety']}]" if case["subtlety"] != "none" else ""
        print(
            f"  {icon} [{i+1:2d}/{len(cases)}] {status:4s}  "
            f"expect={expected:6s} got={actual:6s}  "
            f"conf={verdict.confidence:.3f}  "
            f"{elapsed_ms:6.1f}ms  "
            f"{case['file']} {subtlety_tag}"
        )

        if not match and verdict.chunks:
            bad_chunks = [c for c in verdict.chunks if c.injection]
            if bad_chunks:
                for bc in bad_chunks[:2]:
                    print(f"         flagged chunk {bc.chunk_index}: {bc.chunk_text[:80]}...")
            elif expected == "REJECT":
                print(f"         highest injection score: {verdict.confidence:.3f}")

        results.append({
            **case,
            "result": status,
            "actual": actual,
            "confidence": verdict.confidence,
            "chunks_total": verdict.chunks_total,
            "chunks_injection": verdict.chunks_injection,
            "time_ms": round(elapsed_ms, 1),
        })

    # ── Summary ──
    print(f"\n{'=' * 70}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(cases)}")
    print(f"{'=' * 70}")

    # Breakdown by expected type
    legit_cases = [r for r in results if r["expected"] == "PASS"]
    injected_cases = [r for r in results if r["expected"] == "REJECT"]

    if legit_cases:
        legit_correct = sum(1 for r in legit_cases if r["result"] == "PASS")
        print(f"\nLegitimate (should PASS):  {legit_correct}/{len(legit_cases)} correct")
        print(f"  False positive rate: {(len(legit_cases) - legit_correct) / len(legit_cases) * 100:.1f}%")

    if injected_cases:
        inj_correct = sum(1 for r in injected_cases if r["result"] == "PASS")
        # "PASS" for injected cases means the test passed (injection was caught)
        # Wait, let me re-check. For injected cases, expected="REJECT", so result="PASS" means injection was caught
        inj_caught = sum(1 for r in injected_cases if r["result"] == "PASS")
        print(f"\nInjected (should REJECT):  {len(injected_cases)} total")
        print(f"  Detected:  {inj_caught}/{len(injected_cases)}")
        print(f"  Missed:    {len(injected_cases) - inj_caught}/{len(injected_cases)}")
        if len(injected_cases) > 0:
            print(f"  Detection rate: {inj_caught / len(injected_cases) * 100:.1f}%")

    # Subtlety breakdown for injected cases
    if injected_cases:
        print(f"\nDetection by subtlety:")
        for level in ["obvious", "moderate", "subtle"]:
            level_cases = [r for r in injected_cases if r["subtlety"] == level]
            if level_cases:
                level_caught = sum(1 for r in level_cases if r["result"] == "PASS")
                bar = "█" * level_caught + "░" * (len(level_cases) - level_caught)
                print(f"  {level:10s}: {level_caught}/{len(level_cases)}  {bar}")

    # Timing
    times = [r["time_ms"] for r in results if "time_ms" in r]
    if times:
        print(f"\nTiming: avg={sum(times)/len(times):.1f}ms  "
              f"min={min(times):.1f}ms  max={max(times):.1f}ms")

    if false_positives:
        print(f"\n⚠ FALSE POSITIVES (legitimate content flagged as injection):")
        for fp in false_positives:
            print(f"  - {fp}")

    if false_negatives:
        print(f"\n⚠ FALSE NEGATIVES (injection not detected):")
        for fn in false_negatives:
            print(f"  - {fn}")

    # JSON output
    if json_output:
        report = {
            "profile": profile,
            "total": len(cases),
            "passed": passed,
            "failed": failed,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "results": results,
        }
        report_path = PROJECT_DIR / "corpus-test-report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nJSON report: {report_path}")

    return failed == 0


def main():
    parser = argparse.ArgumentParser(
        description="DEJECTOR corpus test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 test_corpus.py                          # Default: email profile
  python3 test_corpus.py --profile document       # Document profile
  python3 test_corpus.py --subtlety subtle        # Only test subtle injections
  python3 test_corpus.py --category jailbreak     # Only jailbreak attempts
  python3 test_corpus.py --json                   # Save JSON report
        """,
    )
    parser.add_argument("--profile", choices=["email", "skill", "document", "fast"],
                        default="email", help="Scan profile (default: email)")
    parser.add_argument("--threshold", type=float, help="Override threshold")
    parser.add_argument("--no-ensemble", action="store_true", help="Disable ensemble mode")
    parser.add_argument("--category", help="Filter by category (e.g. direct_injection, jailbreak)")
    parser.add_argument("--subtlety", choices=["none", "obvious", "moderate", "subtle"],
                        help="Filter by subtlety level")
    parser.add_argument("--json", action="store_true", help="Save JSON report")
    args = parser.parse_args()

    ensemble = False if args.no_ensemble else None

    all_passed = run_tests(
        profile=args.profile,
        threshold=args.threshold,
        ensemble=ensemble,
        category_filter=args.category,
        subtlety_filter=args.subtlety,
        json_output=args.json,
    )

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
