#!/usr/bin/env python3
"""
DEJECTOR Install — Gated skill installation.

Downloads a skill, scans it for prompt injection, and only installs if clean.
If rejected, the skill is left in quarantine and the user is warned.

Usage:
    python3 dejector_install.py <source> [--skills-dir ~/.openclaw/skills]

Source can be:
    - GitHub URL: https://github.com/openclaw/skills/tree/main/skills/owner/skill-name
    - GitHub raw: https://raw.githubusercontent.com/openclaw/skills/main/skills/owner/skill-name
    - clawhub slug: owner/skill-name
    - Local path: /path/to/skill/

Exit codes:
    0 = installed successfully
    1 = rejected by DEJECTOR (injection detected)
    2 = error (download failed, not found, etc.)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from dejector_core import DejectorScanner

SKILLS_REPO_RAW = "https://raw.githubusercontent.com/openclaw/skills/main/skills"
DEFAULT_SKILLS_DIR = Path.home() / ".openclaw" / "skills"


def parse_source(source: str) -> dict:
    """
    Parse the source into components.
    Returns {owner, name, raw_base_url} or {local_path}.
    """
    # Local path
    if source.startswith("/") or source.startswith("./") or source.startswith("~/"):
        return {"local_path": Path(os.path.expanduser(source))}

    # Full GitHub URL
    # https://github.com/openclaw/skills/tree/main/skills/owner/skill-name
    gh_match = re.match(
        r"https?://github\.com/openclaw/skills/tree/[^/]+/skills/([^/]+)/([^/\s#]+)",
        source,
    )
    if gh_match:
        return {"owner": gh_match.group(1), "name": gh_match.group(2)}

    # Raw GitHub URL
    # https://raw.githubusercontent.com/openclaw/skills/main/skills/owner/skill-name
    raw_match = re.match(
        r"https?://raw\.githubusercontent\.com/openclaw/skills/main/skills/([^/]+)/([^/\s#]+)",
        source,
    )
    if raw_match:
        return {"owner": raw_match.group(1), "name": raw_match.group(2)}

    # slug: owner/skill-name
    slug_match = re.match(r"^([^/]+)/([^/\s#]+)$", source)
    if slug_match:
        return {"owner": slug_match.group(1), "name": slug_match.group(2)}

    # Just a name — search for it
    return {"name": source, "owner": None}


def download_from_github(owner: str, name: str, dest: Path) -> bool:
    """Download a skill from GitHub raw URLs. Returns True on success."""
    base = f"{SKILLS_REPO_RAW}/{owner}/{name}"
    files_to_try = ["SKILL.md", "_meta.json", "README.md", "package.json"]

    found_any = False
    for fname in files_to_try:
        url = f"{base}/{fname}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dejector-install"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                (dest / fname).write_bytes(data)
                found_any = True
        except urllib.error.HTTPError:
            if fname == "SKILL.md":
                # SKILL.md is required
                return False

    return found_any


def download_from_local(src: Path, dest: Path) -> bool:
    """Copy skill from local path. Returns True on success."""
    if not src.exists():
        return False
    if not (src / "SKILL.md").exists():
        # Maybe src IS the SKILL.md
        if src.name == "SKILL.md" or src.suffix == ".md":
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / "SKILL.md")
            return True
        return False
    shutil.copytree(src, dest, dirs_exist_ok=True)
    return True


def install_skill(
    source: str,
    skills_dir: Path = DEFAULT_SKILLS_DIR,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Download, scan, and install a skill.
    Returns exit code: 0=installed, 1=rejected, 2=error.
    """
    parsed = parse_source(source)

    with tempfile.TemporaryDirectory(prefix="dejector-") as tmpdir:
        tmp = Path(tmpdir)

        # Step 1: Download
        print(f"Downloading skill from: {source}")

        if "local_path" in parsed:
            src_path = parsed["local_path"]
            if not download_from_local(src_path, tmp):
                print(f"ERROR: Could not find SKILL.md at {src_path}", file=sys.stderr)
                return 2
            skill_name = src_path.name
        else:
            owner = parsed.get("owner")
            name = parsed.get("name")
            if not name:
                print("ERROR: Could not parse skill source", file=sys.stderr)
                return 2

            if not owner:
                print("ERROR: Owner required. Use format: owner/skill-name", file=sys.stderr)
                return 2

            if not download_from_github(owner, name, tmp):
                print(f"ERROR: Could not download {owner}/{name} from GitHub", file=sys.stderr)
                return 2
            skill_name = name

        # Step 2: Scan with DEJECTOR
        skill_md = tmp / "SKILL.md"
        if not skill_md.exists():
            print("ERROR: No SKILL.md found in downloaded skill", file=sys.stderr)
            return 2

        text = skill_md.read_text(encoding="utf-8", errors="replace")
        print(f"Scanning with DEJECTOR (profile=skill)...")

        scanner = DejectorScanner(profile="skill")
        verdict = scanner.scan_text(text, filename=f"{skill_name}/SKILL.md")

        print(verdict.summary())

        if not verdict.safe:
            if not force:
                print(f"\nREJECTED: {skill_name} contains potential prompt injection.")
                print(f"Confidence: {verdict.confidence:.3f}")
                print(f"\nThe skill has been left in: {tmp}")
                print("To install anyway (NOT recommended), use:")
                print(f"  cp -r '{tmp}' '{skills_dir / skill_name}'")
                return 1
            else:
                print("\nWARNING: Installing despite rejection (--force flag)")

        # Step 3: Install
        dest = skills_dir / skill_name
        if dry_run:
            print(f"\n[DRY RUN] Would install to: {dest}")
            return 0

        skills_dir.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            print(f"Removing existing skill at {dest}")
            shutil.rmtree(dest)

        shutil.copytree(tmp, dest)
        print(f"\nINSTALLED: {skill_name} → {dest}")
        return 0


def main():
    parser = argparse.ArgumentParser(
        prog="dejector-install",
        description="Gated skill installation — scans for injection before installing",
    )
    parser.add_argument("source", help="Skill source (URL, slug owner/name, or local path)")
    parser.add_argument("--skills-dir", default=str(DEFAULT_SKILLS_DIR),
                        help=f"Skills directory (default: {DEFAULT_SKILLS_DIR})")
    parser.add_argument("--force", action="store_true",
                        help="Install even if rejected (NOT recommended)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Download and scan but don't install")

    args = parser.parse_args()
    result = install_skill(
        source=args.source,
        skills_dir=Path(args.skills_dir),
        force=args.force,
        dry_run=args.dry_run,
    )
    sys.exit(result)


if __name__ == "__main__":
    main()
