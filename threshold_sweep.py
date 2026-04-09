#!/usr/bin/env python3
"""
Threshold sweep for DEJECTOR — find the optimal confidence threshold.

Tests the email profile corpus at multiple thresholds and reports
detection rate vs false positive rate for each.
"""

import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

# Add venv site-packages
_venv_site = PROJECT_DIR / "venv" / "lib"
if _venv_site.exists():
    for _p in _venv_site.glob("python*/site-packages"):
        sys.path.insert(0, str(_p))

TESTS_DIR = PROJECT_DIR / "tests"
MANIFEST = TESTS_DIR / "corpus-manifest.json"


def main():
    from dejector_core import DejectorScanner

    manifest = json.loads(MANIFEST.read_text())
    cases = manifest["cases"]

    thresholds = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]

    print("DEJECTOR Threshold Sweep")
    print("=" * 80)
    print(f"Test cases: {len(cases)} ({sum(1 for c in cases if c['expected']=='PASS')} legit, "
          f"{sum(1 for c in cases if c['expected']=='REJECT')} injected)")
    print(f"Mode: ensemble (both models must agree)")
    print(f"{'=' * 80}\n")

    # Load scanner once
    scanner = DejectorScanner(profile="email")
    scanner._ensure_loaded()

    # Pre-scan all texts once to get per-chunk raw scores
    # We need to re-classify per threshold, so let's just scan once
    # and store the results
    all_chunk_results = []
    for case in cases:
        filepath = TESTS_DIR / case["file"]
        text = filepath.read_text(encoding="utf-8", errors="replace")

        from dejector_core import _chunk_text
        chunks = _chunk_text(text, 512)
        chunk_scores = []
        for chunk in chunks:
            r1 = scanner._pipe1(chunk)[0]
            label1 = r1["label"].upper()
            score1 = r1["score"]
            is_inj1 = label1 in ("INJECTION", "1", "LABEL_1")
            inj_score1 = score1 if is_inj1 else (1.0 - score1)

            r2 = scanner._pipe2(chunk)[0]
            label2 = r2["label"].upper()
            score2 = r2["score"]
            is_inj2 = label2 in ("INJECTION", "1", "LABEL_1")
            inj_score2 = score2 if is_inj2 else (1.0 - score2)

            chunk_scores.append({
                "inj_score1": inj_score1,
                "inj_score2": inj_score2,
            })
        all_chunk_results.append({
            "case": case,
            "chunk_scores": chunk_scores,
        })

    # Now sweep thresholds
    print(f"{'Thresh':>6s}  {'Det%':>5s}  {'FP%':>5s}  {'TP':>3s}/{'<3s'}  {'FP':>3s}/{'<3s'}  "
          f"{'Obv':>5s}  {'Mod':>5s}  {'Sub':>5s}  {'Missed files'}")
    print("-" * 120)

    best_threshold = None
    best_score = -1

    for threshold in thresholds:
        tp = 0  # true positives (injection caught)
        fn = 0  # false negatives (injection missed)
        tn = 0  # true negatives (legit passed)
        fp = 0  # false positives (legit flagged)

        missed_files = []
        subtlety_hits = {"obvious": [0, 0], "moderate": [0, 0], "subtle": [0, 0]}

        for entry in all_chunk_results:
            case = entry["case"]
            chunk_scores = entry["chunk_scores"]

            # Ensemble: BOTH models must flag for rejection
            any_injection = any(
                (cs["inj_score1"] >= threshold) and (cs["inj_score2"] >= threshold)
                for cs in chunk_scores
            )

            if case["expected"] == "REJECT":
                if any_injection:
                    tp += 1
                    subtlety_hits[case["subtlety"]][0] += 1
                else:
                    fn += 1
                    missed_files.append(case["file"])
                    subtlety_hits[case["subtlety"]][1] += 1
            else:
                if any_injection:
                    fp += 1
                else:
                    tn += 1

        total_inj = tp + fn
        total_legit = tn + fp
        det_rate = (tp / total_inj * 100) if total_inj else 0
        fp_rate = (fp / total_legit * 100) if total_legit else 0

        obv = f"{subtlety_hits['obvious'][0]}/{sum(subtlety_hits['obvious'])}"
        mod = f"{subtlety_hits['moderate'][0]}/{sum(subtlety_hits['moderate'])}"
        sub = f"{subtlety_hits['subtle'][0]}/{sum(subtlety_hits['subtle'])}"

        missed_str = ", ".join(Path(f).name for f in missed_files[:3])
        if len(missed_files) > 3:
            missed_str += f" (+{len(missed_files)-3} more)"

        # Score: prioritize 0% FP, then maximize detection
        # Penalize FP heavily (10x more than missing an injection)
        score = det_rate - (fp_rate * 10)
        marker = ""
        if fp == 0:
            marker = " ← 0% FP"
        if score > best_score and fp == 0:
            best_score = score
            best_threshold = threshold
            marker = " ← BEST (0% FP)"

        print(f"{threshold:6.2f}  {det_rate:5.1f}  {fp_rate:5.1f}  {tp:>3d}/{total_inj:<3d}  "
              f"{fp:>3d}/{total_legit:<3d}  {obv:>5s}  {mod:>5s}  {sub:>5s}  {missed_str}{marker}")

    print(f"\n{'=' * 80}")
    print(f"Recommended threshold: {best_threshold} (best detection with 0% false positives)")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
