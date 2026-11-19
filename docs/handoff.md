# Handoff

Updated 15 Nov 2026 (pre-bootcamp day). Read this first in a new session.

## What we are building
Belka: an AI marketing assistant on mobile for Thai SME shops. It gives a ready-to-use weekly plan.
"Belka เสนอ เจ้าของร้านตัดสินใจ". Stack: Python >=3.12 with `uv`, Strands Agents, Amazon Bedrock `anthropic.claude-sonnet-5` in ap-southeast-1.

## Decisions made
- Must-have feature for 21 Nov: the weekly plan with captions and reasons (3 tasks). Recorded in `.kiro/steering/product.md`.
- The agent runs on Amazon Bedrock through Strands (not Amazon Quick).
- `design.md` and `tasks.md` are NOT started: the team approves `requirements.md` first.
- Steering modes unchanged: `aws.md` is `always`; the other three have no front matter (always). Not agreed to change.

## Files that matter
- `docs/submission.md`: source of truth for the product.
- `.kiro/steering/` (`aws.md`, `product.md`, `structure.md`, `tech.md`): project rules.
- `.kiro/specs/weekly-plan/requirements.md`: the spec, with 5 open questions at the end.
- `agent.py`: Belka agent, 3 stub tools over fictional shops. `uv run agent.py`, then type `shop-001`.
- `tests/test_agent.py`: smoke test. `.kiro/hooks/test-on-save.json` runs `uv run pytest` on save.
- `check_bedrock.py`: prints `READY` when Bedrock responds.

## Open items
- AWS account: laptop is signed in via SSO (profile `default`, role ai-hackathon, region ap-southeast-1) to the team account 843770387889 (ai-hackaton-sandbox-16, as named by the organisers). `aws sts get-caller-identity` shows 843770387889 and check_bedrock prints READY (16 Nov). It first returned "account is being verified" for a short time, then passed.
- Back up the folder outside the laptop (R2). Confirm the Kiro plan and keep the receipt (R1).

## Single next step
Team answers the open questions and approves `requirements.md`; design starts on 21 Nov.

## Added 18 Nov 2026
- `prototype/`: runnable reference code (Trust Engine, red-line gate, Strands agent with a `check_redline` tool, FastAPI, phone-sized web page, Expo app, 218 tests that do not call AWS). It is NOT the deliverable: `.kiro/specs/weekly-plan/` stays the source of truth, and Kiro builds the real code from its tasks. See `prototype/README.md` for which task each file helps with and where the prototype differs from the spec.
- The prototype follows `aws.md`: `anthropic.claude-sonnet-5` in ap-southeast-1 only, refuses `global.`/`apac.` model IDs, web binds 127.0.0.1.
- New folder not in `structure.md` (listed here per the tasks.md convention): `prototype/`.
- Proposals P-1 (3-tap onboarding), P-2 (one card for today), P-3 (Expo app) appended to `.kiro/steering/product.md`, marked as pending team approval.
- Backups of the two edited files: `_backup-2026-11-18/`.
- Next: team decides P-1 to P-3. If accepted, update `requirements.md` (Req 1, 2.6, 2.8, D1) before running tasks.
