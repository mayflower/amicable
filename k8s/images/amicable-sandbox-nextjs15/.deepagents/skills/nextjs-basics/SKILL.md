---
name: nextjs-basics
description: Quick reference for Next.js 15 (App Router) projects in Amicable.
license: MIT
---

# Next.js Basics

## When To Use
- You are editing a Next.js 15 template.

## Conventions
- App Router: routes live under `src/app/`.
- Prefer Server Components by default; add `"use client"` only when needed.
- For data fetching to Hasura, you can use `fetch` from server components or a small client wrapper.

## Common Scripts
- `npm run lint`
- `npm run build`
