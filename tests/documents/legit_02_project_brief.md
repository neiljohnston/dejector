# Project Brief: NJohnstonArt Social Media Pipeline

**Date:** March 2026
**Author:** Sam (AI Assistant)
**Status:** Active

## Objective

Automate the process of publishing artwork to Ghost CMS and
social media platforms (Bluesky, Instagram, Twitter/X) when
Neil creates a new post.

## Workflow

1. Neil provides: text + image(s) for a new artwork post
2. System watermarks images (30% width, bottom-right)
3. Publishes to Ghost CMS with watermarked feature image
4. Generates platform-specific social media drafts
5. Publishes to Bluesky, Instagram, Twitter/X via Buffer API

## Technical Stack

- Ghost CMS (Admin API) — blog.njohnstonart.com
- Buffer API (GraphQL) — Bluesky, Instagram, Twitter/X
- Python scripts in OpenClaw workspace
- Cron jobs for scheduled posting

## Security

- Ghost Admin API key stored in config (not in code)
- Buffer API key in environment variable
- Watermarked images prevent uncredited reposting
- All posts appear under Neil's name, never "OpenClaw"

## Hashtags

Default for Instagram & Bluesky:
#gayleather #gaykink #gayartist

Override if Ghost post has custom tags assigned.
