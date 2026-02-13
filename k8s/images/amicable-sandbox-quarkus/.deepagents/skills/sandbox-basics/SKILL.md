---
name: sandbox-basics
description: Quick reference for Quarkus/Maven sandbox workflow.
license: MIT
---

# Sandbox Basics

## When To Use
- You are editing the Quarkus sandbox template.
- You need deterministic compile/test checks before finishing.

## Checklist
- Use Quarkus dev mode for preview: `./mvnw quarkus:dev -Dquarkus.http.host=0.0.0.0 -Dquarkus.http.port=3000`.
- Prefer deterministic checks: `./mvnw -q -DskipTests compile` and `./mvnw -q test`.
- Keep resource/controller changes small and validated.

## Verify
- Run compile and ensure no build errors.
- Run tests when present.
- Confirm preview endpoint still serves on port `3000`.
