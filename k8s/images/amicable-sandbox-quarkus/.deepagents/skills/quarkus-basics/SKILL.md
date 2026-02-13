---
name: quarkus-basics
description: Execution-ready guidance for Quarkus REST resources and service boundaries.
license: MIT
---

# Quarkus Basics

## When To Use
- You are editing the Quarkus template.
- You are adding REST resources, service logic, or config-driven behavior.

## Implementation Rules
- Keep JAX-RS resources focused on HTTP transport concerns.
- Move business logic into CDI-managed services.
- Keep configuration explicit in `application.properties`.
- Prefer small, testable classes with clear responsibilities.

## Sandbox Notes
- Preview uses Quarkus dev mode on `0.0.0.0:3000`.
- Use fast compile/test loops before finalizing.

## Verify
- Run `./mvnw -q -DskipTests compile`.
- Run `./mvnw -q test` when tests exist.
- Confirm updated resources respond correctly in preview.
