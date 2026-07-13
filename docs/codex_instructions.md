---
status: draft
---

# Codex Instructions

## Draft Status

All Markdown files under `docs/` are drafts and are not approved for production use.

1. Do not load, inject, parse, or otherwise use these Markdown files in roof-processing logic, AI prompts, scoring, recommendations, cost estimation, or report generation.
2. Do not treat draft content, business rules, scoring weights, or reference-library guidance as an active engineering specification.
3. Introduce documentation into processing only after the user explicitly approves the relevant file and roof type.
4. Keep activation roof-type-specific so one approved roof system does not implicitly activate draft guidance for another roof system.
5. Never hard-code draft business rules or draft scoring weights into application code.
6. Preserve the current processing architecture unless instructed otherwise.
7. Ask before introducing breaking architectural changes.
