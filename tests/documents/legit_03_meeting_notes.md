# Meeting Notes — April 7, 2026

## Attendees
- Neil Johnston
- Sam (AI Assistant)

## Agenda

### 1. Dejector Project Review
- Core scanner working: DeBERTa ensemble mode
- 257MB primary model + 715MB secondary model
- Ensemble threshold: 0.70 for email, 0.95 for skills
- Speed: ~100ms per scan in ensemble mode

### 2. ClawHub Preparation
- Need test suite before pushing dejector skill
- Should demonstrate scanner catches injections in:
  - Email bodies
  - Documents (markdown, plain text)
  - Skill files (SKILL.md)
- Test corpus should be self-contained, no API calls

### 3. Action Items
- [ ] Generate test corpus of seeded emails and documents
- [ ] Build test runner that scans corpus and reports results
- [ ] Verify detection rates across subtlety levels
- [ ] Document test methodology for README

### 4. Next Steps
- Once tests pass, package for ClawHub
- Create demo video showing the scanner in action
- Write blog post about prompt injection defense
