#!/usr/bin/env python3
"""
DEJECTOR Gmail Scanner — Prompt injection blocking gate for email.

Scans unread emails via gog or gws CLI, flags/rejects those containing
prompt injection attempts, and produces a report.

Supports both:
  - gog (github.com/steipete/gogcli)
  - gws (github.com/googleworkspace/cli)

Usage:
    python3 dejector_gmail.py scan                    # Scan unread emails
    python3 dejector_gmail.py scan --max 50           # Scan up to 50
    python3 dejector_gmail.py scan --dry-run          # Scan but don't label
    python3 dejector_gmail.py scan --cli gws          # Force gws
    python3 dejector_gmail.py scan --cli gog          # Force gog
    python3 dejector_gmail.py check                   # Check which CLI is available
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from dejector_core import DejectorScanner

SPAM_LABEL = "DEJECTOR-Rejected"
LOG_DIR = PROJECT_DIR / "gmail-logs"


def detect_cli() -> str:
    """Detect which Gmail CLI is available. Returns 'gog' or 'gws'."""
    gog = shutil.which("gog")
    gws = shutil.which("gws")
    if gog:
        return "gog"
    elif gws:
        return "gws"
    else:
        raise RuntimeError("Neither gog nor gws CLI found. Install one of them.")


def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"


class GogBackend:
    """Gmail backend using gog CLI."""

    def list_unread(self, max_emails: int = 25) -> list[dict]:
        """List unread emails. Returns list of {id, threadId, subject, from, date}."""
        cmd = [
            "gog", "gmail", "search",
            "is:unread", "in:inbox",
            "--max", str(max_emails),
            "--json",
        ]
        rc, stdout, stderr = run_cmd(cmd)
        if rc != 0:
            raise RuntimeError(f"gog search failed: {stderr}")

        data = json.loads(stdout)
        threads = data.get("threads", [])
        # Flatten to individual messages
        messages = []
        for thread in threads:
            thread_id = thread.get("id", "")
            # Get full thread to extract individual messages
            cmd2 = ["gog", "gmail", "thread", "get", thread_id, "--json"]
            rc2, stdout2, stderr2 = run_cmd(cmd2)
            if rc2 != 0:
                continue
            thread_data = json.loads(stdout2)
            for msg in thread_data.get("messages", []):
                msg_id = msg.get("id", "")
                headers = {
                    h["name"].lower(): h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }
                # Only include unread
                label_ids = msg.get("labelIds", [])
                if "UNREAD" not in label_ids:
                    continue
                messages.append({
                    "id": msg_id,
                    "threadId": thread_id,
                    "subject": headers.get("subject", "(no subject)"),
                    "from": headers.get("from", "(unknown)"),
                    "date": headers.get("date", ""),
                })
        return messages

    def get_body(self, message_id: str) -> str:
        """Get the text body of a message."""
        cmd = ["gog", "gmail", "get", message_id, "--json"]
        rc, stdout, stderr = run_cmd(cmd)
        if rc != 0:
            raise RuntimeError(f"gog get failed: {stderr}")
        data = json.loads(stdout)
        return self._extract_body(data)

    def _extract_body(self, message: dict) -> str:
        """Extract text body from a Gmail message payload."""
        payload = message.get("payload", {})
        body_parts = []

        def walk_parts(part, depth=0):
            mime = part.get("mimeType", "")
            if mime == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    import base64
                    try:
                        decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                        body_parts.append(decoded)
                    except Exception:
                        pass
            elif mime == "text/html" and not body_parts:
                # Fall back to HTML if no plain text found
                data = part.get("body", {}).get("data", "")
                if data:
                    import base64
                    try:
                        decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                        # Strip HTML tags for scanning
                        import re
                        text = re.sub(r"<[^>]+>", " ", decoded)
                        text = re.sub(r"\s+", " ", text).strip()
                        body_parts.append(text)
                    except Exception:
                        pass
            for sub in part.get("parts", []):
                walk_parts(sub, depth + 1)

        walk_parts(payload)
        return "\n".join(body_parts)

    def apply_label(self, message_id: str, label_name: str) -> bool:
        """Apply a label to a message. Creates label if needed."""
        # First, try to find existing label
        rc, stdout, stderr = run_cmd(["gog", "gmail", "labels", "--json"])
        if rc == 0:
            labels = json.loads(stdout)
            label_id = None
            for label in labels:
                if label.get("name", "").lower() == label_name.lower():
                    label_id = label.get("id")
                    break
            if not label_id:
                # Create label
                rc2, stdout2, stderr2 = run_cmd([
                    "gog", "gmail", "labels", "create",
                    "--name", label_name,
                    "--json",
                ])
                if rc2 == 0:
                    label_data = json.loads(stdout2)
                    label_id = label_data.get("id")
            if label_id:
                # Apply label
                rc3, _, _ = run_cmd([
                    "gog", "gmail", "thread", "modify", message_id,
                    "--add-label", label_id,
                ])
                return rc3 == 0
        return False

    def mark_as_spam(self, message_id: str) -> bool:
        """Move message to spam."""
        # Remove INBOX, add SPAM
        rc, _, _ = run_cmd([
            "gog", "gmail", "thread", "modify", message_id,
            "--add-label", "SPAM",
            "--remove-label", "INBOX",
        ])
        return rc == 0


class GwsBackend:
    """Gmail backend using gws CLI."""

    def list_unread(self, max_emails: int = 25) -> list[dict]:
        """List unread emails."""
        cmd = [
            "gws", "gmail", "users", "messages", "list",
            "--user-id", "me",
            "--q", "is:unread in:inbox",
            "--max-results", str(max_emails),
            "--format", "json",
        ]
        rc, stdout, stderr = run_cmd(cmd)
        if rc != 0:
            raise RuntimeError(f"gws list failed: {stderr}")

        data = json.loads(stdout)
        messages_raw = data.get("messages", [])
        if not messages_raw:
            # Try alternate structure
            if isinstance(data, list):
                messages_raw = data

        messages = []
        for msg_ref in messages_raw[:max_emails]:
            msg_id = msg_ref.get("id", "") if isinstance(msg_ref, dict) else str(msg_ref)
            if not msg_id:
                continue
            # Get full message
            cmd2 = [
                "gws", "gmail", "users", "messages", "get",
                "--user-id", "me",
                "--id", msg_id,
                "--format", "json",
            ]
            rc2, stdout2, stderr2 = run_cmd(cmd2)
            if rc2 != 0:
                continue
            msg = json.loads(stdout2)
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            messages.append({
                "id": msg_id,
                "threadId": msg.get("threadId", ""),
                "subject": headers.get("subject", "(no subject)"),
                "from": headers.get("from", "(unknown)"),
                "date": headers.get("date", ""),
            })
        return messages

    def get_body(self, message_id: str) -> str:
        """Get the text body of a message."""
        cmd = [
            "gws", "gmail", "users", "messages", "get",
            "--user-id", "me",
            "--id", message_id,
            "--format", "json",
        ]
        rc, stdout, stderr = run_cmd(cmd)
        if rc != 0:
            raise RuntimeError(f"gws get failed: {stderr}")
        data = json.loads(stdout)
        return self._extract_body(data)

    def _extract_body(self, message: dict) -> str:
        """Extract text body from a Gmail message payload."""
        payload = message.get("payload", {})
        body_parts = []

        def walk_parts(part, depth=0):
            mime = part.get("mimeType", "")
            if mime == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    import base64
                    try:
                        decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                        body_parts.append(decoded)
                    except Exception:
                        pass
            elif mime == "text/html" and not body_parts:
                data = part.get("body", {}).get("data", "")
                if data:
                    import base64
                    try:
                        decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                        import re
                        text = re.sub(r"<[^>]+>", " ", decoded)
                        text = re.sub(r"\s+", " ", text).strip()
                        body_parts.append(text)
                    except Exception:
                        pass
            for sub in part.get("parts", []):
                walk_parts(sub, depth + 1)

        walk_parts(payload)
        return "\n".join(body_parts)

    def mark_as_spam(self, message_id: str) -> bool:
        """Move message to spam."""
        cmd = [
            "gws", "gmail", "users", "messages", "modify",
            "--user-id", "me",
            "--id", message_id,
            "--add-label-ids", "SPAM",
            "--remove-label-ids", "INBOX",
            "--format", "json",
        ]
        rc, _, _ = run_cmd(cmd)
        return rc == 0


def get_backend(cli: str | None = None) -> object:
    """Get the appropriate Gmail backend."""
    if cli is None:
        cli = detect_cli()
    if cli == "gog":
        return GogBackend()
    elif cli == "gws":
        return GwsBackend()
    else:
        raise ValueError(f"Unknown CLI: {cli}")


def scan_emails(
    cli: str | None = None,
    max_emails: int = 25,
    dry_run: bool = False,
    threshold: float = 0.7,
):
    """Scan unread emails and flag rejections."""
    backend = get_backend(cli)
    detected_cli = cli or detect_cli()

    print(f"Using CLI: {detected_cli}")
    print(f"Fetching unread emails (max={max_emails})...")

    try:
        messages = backend.list_unread(max_emails)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return []

    if not messages:
        print("No unread emails found.")
        return []

    print(f"Found {len(messages)} unread emails\n")

    print("Initializing DEJECTOR scanner (profile=email)...")
    scanner = DejectorScanner(profile="email")

    results = []
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

    for i, msg in enumerate(messages):
        msg_id = msg["id"]
        subject = msg["subject"]
        sender = msg["from"]

        print(f"  [{i+1}/{len(messages)}] {sender[:30]}: {subject[:50]}...", end=" ", flush=True)

        try:
            body = backend.get_body(msg_id)
        except RuntimeError as e:
            print(f"ERROR reading: {e}")
            continue

        if not body.strip():
            print("SKIP (empty body)")
            continue

        verdict = scanner.scan_text(body, filename=f"email:{msg_id}")

        status = "CLEAN" if verdict.safe else "REJECTED"
        print(f"{status} (conf: {verdict.confidence:.3f})")

        result = {
            "timestamp": datetime.now().isoformat(),
            "message_id": msg_id,
            "thread_id": msg.get("threadId", ""),
            "from": sender,
            "subject": subject,
            "verdict": status,
            "confidence": f"{verdict.confidence:.4f}",
            "chunks_total": verdict.chunks_total,
            "chunks_injection": verdict.chunks_injection,
        }
        results.append(result)

        # Log entry
        with open(log_file, "a") as f:
            f.write(json.dumps(result) + "\n")

        # Take action on rejection
        if not verdict.safe:
            if dry_run:
                print(f"    [DRY RUN] Would mark as spam: {subject}")
            else:
                ok = backend.mark_as_spam(msg_id)
                if ok:
                    print(f"    → Moved to spam")
                else:
                    print(f"    → Failed to move to spam (manual review needed)")

    # Summary
    clean = sum(1 for r in results if r["verdict"] == "CLEAN")
    rejected = sum(1 for r in results if r["verdict"] == "REJECTED")
    print(f"\n{'='*60}")
    print(f"GMAIL SCAN RESULTS: {clean} clean, {rejected} rejected out of {len(results)}")
    print(f"Log: {log_file}")
    print(f"{'='*60}")

    return results


def main():
    parser = argparse.ArgumentParser(
        prog="dejector-gmail",
        description="DEJECTOR Gmail scanner — block prompt injections in email",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Check command
    check_parser = subparsers.add_parser("check", help="Check which Gmail CLI is available")
    check_parser.set_defaults(func=lambda args: print(f"Detected CLI: {detect_cli()}"))

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan unread emails")
    scan_parser.add_argument("--cli", choices=["gog", "gws"], help="Force which CLI to use")
    scan_parser.add_argument("--max", type=int, default=25, help="Max emails to scan")
    scan_parser.add_argument("--dry-run", action="store_true", help="Scan but don't label")
    scan_parser.set_defaults(func=lambda args: scan_emails(
        cli=args.cli,
        max_emails=args.max,
        dry_run=args.dry_run,
    ))

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(2)
    args.func(args)


if __name__ == "__main__":
    main()
