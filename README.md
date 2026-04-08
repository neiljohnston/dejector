# DEJECTOR — Prompt Injection Defense

🛡️ Scanner that detects prompt injection in emails, documents, and AI agent skills before they reach your agent.

## Why DEJECTOR?

AI agents like OpenClaw process untrusted content — emails, uploaded documents, community skills. Any of these can contain **prompt injection attacks**: hidden instructions designed to manipulate the agent into leaking data, executing commands, or behaving unexpectedly.

DEJECTOR sits between untrusted content and your agent as a blocking gate.

## How It Works

Two fine-tuned DeBERTa classifiers scan text for injection patterns:

| Model | Size | Speed | Role |
|-------|------|-------|------|
| [testsavantai/prompt-injection-defender-base-v0](https://huggingface.co/testsavantai/prompt-injection-defender-base-v0) | 257MB | ~37ms | Primary |
| [deepset/deberta-v3-base-injection](https://huggingface.co/deepset/deberta-v3-base-injection) | 715MB | ~60ms | Ensemble confirm |

In ensemble mode, both must agree for rejection. This eliminates false positives while catching real attacks.

**Key insight:** These are classifiers, not LLMs. They output `SAFE`/`INJECTION` labels only — no text generation, no prompt to jailbreak, no way to "talk them into" bypassing themselves.

## Install

```bash
pip install dejector
```

Or from source:

```bash
git clone https://github.com/njohnston/dejector.git
cd dejector
pip install -e .
dejector test --profile email
```

## Quick Start

```bash
# Scan a file
dejector scan email.txt --profile email

# Scan unread Gmail
dejector gmail scan --dry-run

# Install a skill (gated)
dejector install owner/skill-name

# Run test suite
dejector test --profile email
```

## Profiles

| Profile | Threshold | Ensemble | Use Case |
|---------|-----------|----------|----------|
| `email` | 0.70 | Yes | Emails (strict) |
| `skill` | 0.95 | Yes | OpenClaw skills (relaxed — instructions expected) |
| `document` | 0.70 | Yes | Uploaded documents |
| `fast` | 0.70 | No | Quick single-model scan |

## Python API

```python
from dejector import DejectorScanner

scanner = DejectorScanner(profile="email")
verdict = scanner.scan_text("Some text...")

print(verdict.safe)           # True/False
print(verdict.confidence)     # 0.0-1.0
print(verdict.chunks)         # Per-chunk results
```

## Commands

### `dejector scan`
Scan files or stdin for injection.

```
dejector scan <file> [--profile email|skill|document|fast]
                     [--ensemble] [--threshold 0.7]
                     [--json] [--quarantine-dir /path]
```

### `dejector gmail scan`
Scan unread emails via `gog` or `gws` CLI.

```
dejector gmail scan [--cli gog|gws] [--max 25] [--dry-run]
```

Clean emails stay in inbox. Rejected emails move to spam.

### `dejector install`
Gated skill installation.

```
dejector install <source> [--skills-dir ~/.openclaw/skills] [--dry-run]
```

Sources: `owner/slug`, GitHub URL, or local path. Scans SKILL.md before installing.

### `dejector test`
Run built-in test cases.

```
dejector test [--profile email|skill] [--ensemble]
```

## OpenClaw Skill

DEJECTOR includes an OpenClaw skill that tells your agent to:
1. Always scan emails through `dejector gmail scan` before processing
2. Always install skills through `dejector install` (never download directly)
3. Never process rejected content

Install the skill:
```bash
openclaw skills install dejector
```

## Test Results

**Email profile (threshold 0.70, ensemble):**
- 8/8 test cases pass (5 injection, 3 legitimate)
- 100% true positive rate
- 0% false positive rate

**Skill profile (threshold 0.95, ensemble):**
- 21/25 random ClawHub skills pass clean (84%)
- 4 flagged with 0.998+ confidence (legitimate instruction-like patterns)

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Gmail API   │────▶│  DEJECTOR CLI    │────▶│  OpenClaw    │
│  (gog/gws)   │     │  (scanner)       │     │  (agent)     │
└─────────────┘     │                  │     └─────────────┘
                    │ ┌──────────────┐ │
                    │ │ DeBERTa #1   │ │       ┌─────────────┐
                    │ │ (257MB)      │ │──────▶│  Spam /     │
                    │ └──────────────┘ │       │  Quarantine │
                    │ ┌──────────────┐ │       └─────────────┘
                    │ │ DeBERTa #2   │ │
                    │ │ (715MB)      │ │
                    │ └──────────────┘ │
                    └──────────────────┘
```

## License

MIT
