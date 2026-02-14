---
name: sandbox-preview-contract
description: Non-negotiable preview and QA constraints for Amicable sandbox templates.
license: MIT
---

# Sandbox Preview Contract

## When To Use
- You are implementing features inside any Amicable sandbox template.
- You need to keep the app compatible with the preview runtime and deterministic QA loop.

## Non-Negotiables
- Keep the preview server reachable at `0.0.0.0:3000`.
- Make small, incremental edits and verify after each meaningful step.
- Prefer deterministic checks before finishing (lint/typecheck/build or compile/test equivalents).
- Do not rely on hidden local machine state; everything must work in the sandbox workspace.

## Workflow
- Read `/AGENTS.md` first for template-specific commands.
- Apply the minimum code change that satisfies the request.
- Run the template QA commands listed in `/AGENTS.md`.
- If a check fails, fix the failure before moving to the next feature change.

## Verify
- Confirm the app preview is still reachable on port `3000`.
- Run the template's deterministic QA command set from `/AGENTS.md`.
- Validate that changed routes/pages/endpoints render or respond as expected.
