#!/usr/bin/env python3
"""
DEJECTOR Test Harness — Blind skill injection scan.

Reads skills from a local clone of the OpenClaw skills repo,
picks 25 random ones, scans their SKILL.md with DEJECTOR,
and produces a CSV report.

The operator (Sam) does NOT look at skill contents during this test.

Repo structure: skills/<owner>/<skill-name>/SKILL.md
                skills/<owner>/<skill-name>/_meta.json
"""

import csv
import json
import random
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from dejector_core import DejectorScanner

REPO_DIR = PROJECT_DIR / "skills-repo" / "skills"
QUARANTINE_DIR = PROJECT_DIR / "test-quarantine"
CLEAN_DIR = PROJECT_DIR / "test-clean"
REJECTED_DIR = PROJECT_DIR / "test-rejected"
REPORT_FILE = PROJECT_DIR / "test-report.csv"


def find_all_skills() -> list[dict]:
    skills = []
    for owner_dir in sorted(REPO_DIR.iterdir()):
        if not owner_dir.is_dir():
            continue
        for skill_md in owner_dir.rglob("SKILL.md"):
            skill_path = skill_md.parent
            rel = skill_path.relative_to(REPO_DIR)
            slug = str(rel).replace("/", "-")
            owner = str(rel.parts[0])
            skills.append({"slug": slug, "owner": owner, "skill_dir": skill_path})
    print(f"Found {len(skills)} skills with SKILL.md")
    return skills


def copy_skill(skill_info: dict, dest_dir: Path) -> dict | None:
    src_dir = skill_info["skill_dir"]
    slug = skill_info["slug"]
    skill_dir = dest_dir / slug
    skill_dir.mkdir(parents=True, exist_ok=True)

    meta = {}
    meta_src = src_dir / "_meta.json"
    if meta_src.exists():
        meta = json.loads(meta_src.read_text())
        shutil.copy2(meta_src, skill_dir / "_meta.json")
    else:
        meta = {
            "owner": skill_info["owner"],
            "slug": slug,
            "displayName": slug,
            "latest": {"version": "?", "publishedAt": 0, "commit": "?"},
        }
        (skill_dir / "_meta.json").write_text(json.dumps(meta, indent=2))

    shutil.copy2(src_dir / "SKILL.md", skill_dir / "SKILL.md")
    return meta


def scan_skills(
    num_skills: int = 25,
    ensemble: bool = True,
    seed: int | None = None,
    threshold: float = 0.95,
):
    for d in [QUARANTINE_DIR, CLEAN_DIR, REJECTED_DIR]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    all_skills = find_all_skills()

    rng = random.Random(seed)
    selected = rng.sample(all_skills, min(num_skills, len(all_skills)))
    print(f"\nSelected {len(selected)} random skills for scanning\n")

    copied = []
    for i, skill_info in enumerate(selected):
        slug = skill_info["slug"]
        print(f"  [{i+1}/{len(selected)}] Copying {slug}...", end=" ", flush=True)
        meta = copy_skill(skill_info, QUARANTINE_DIR)
        if meta:
            copied.append((slug, meta))
            print("OK")
        else:
            print("SKIP")

    print(f"\n{len(copied)} skills in quarantine\n")

    print(f"Initializing DEJECTOR scanner (profile=skill, threshold={threshold})...")
    scanner = DejectorScanner(profile="skill", threshold=threshold)

    results = []

    for i, (slug, meta) in enumerate(copied):
        skill_md = QUARANTINE_DIR / slug / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8", errors="replace")

        print(f"  [{i+1}/{len(copied)}] Scanning {slug}...", end=" ", flush=True)
        verdict = scanner.scan_text(text, filename=f"{slug}/SKILL.md")

        status = "CLEAN" if verdict.safe else "REJECTED"
        print(f"{status} (conf: {verdict.confidence:.3f})")

        owner = meta.get("owner", "unknown")
        display_name = meta.get("displayName", slug)
        latest = meta.get("latest", {})
        version = latest.get("version", "?")
        published = latest.get("publishedAt", 0)
        if isinstance(published, int) and published > 0:
            pub_date = datetime.fromtimestamp(published / 1000).strftime("%Y-%m-%d")
        else:
            pub_date = "?"

        injection_detail = ""
        if not verdict.safe:
            bad_chunks = [c for c in verdict.chunks if c.injection]
            injection_detail = "; ".join(
                f"chunk {c.chunk_index}: score={c.score:.3f}" for c in bad_chunks[:5]
            )

        result = {
            "slug": slug,
            "display_name": display_name,
            "owner": owner,
            "version": version,
            "published": pub_date,
            "verdict": status,
            "confidence": f"{verdict.confidence:.4f}",
            "chunks_total": verdict.chunks_total,
            "chunks_injection": verdict.chunks_injection,
            "detail": injection_detail,
        }
        results.append(result)

        src = QUARANTINE_DIR / slug
        dest = (CLEAN_DIR if verdict.safe else REJECTED_DIR) / slug
        shutil.move(str(src), str(dest))

    print(f"\nWriting report to {REPORT_FILE}")
    with open(REPORT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "slug", "display_name", "owner", "version", "published",
            "verdict", "confidence", "chunks_total", "chunks_injection", "detail",
        ])
        writer.writeheader()
        writer.writerows(results)

    clean = sum(1 for r in results if r["verdict"] == "CLEAN")
    rejected = sum(1 for r in results if r["verdict"] == "REJECTED")
    print(f"\n{'='*60}")
    print(f"RESULTS: {clean} clean, {rejected} rejected out of {len(results)} skills")
    print(f"Clean skills:    {CLEAN_DIR}")
    print(f"Rejected skills: {REJECTED_DIR}")
    print(f"Report:          {REPORT_FILE}")
    print(f"{'='*60}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DEJECTOR blind skill test harness")
    parser.add_argument("-n", "--num", type=int, default=25)
    parser.add_argument("--no-ensemble", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--threshold", type=float, default=0.95,
                        help="Injection confidence threshold for skills (default 0.95)")
    args = parser.parse_args()

    scan_skills(
        num_skills=args.num,
        ensemble=not args.no_ensemble,
        seed=args.seed,
        threshold=args.threshold,
    )
