# CLAUDE.md — project memory for the SEO Command Center build

This file is your **context / memory for the AI**. Claude Code loads it automatically every
session. Strong builders engineer this file instead of re-explaining everything in chat — it
is one of the clearest signals of good practice, and it is graded (see the challenge brief
section 08). Keep it short, specific, and update it as you learn.

Replace the prompts below with your own. This is YOUR file.

## What we are building
A Claude Code plugin that ingests a Screaming Frog SEO export (`internal_all.csv` + issue
CSVs), audits it against the rulebook, prioritizes issues, writes fixes, serves a live
dashboard at localhost:7700, and outputs `outputs/report.json` + `outputs/report.html`.

## Hard rules (the agent must follow these)
- Detect issues in **plain Python** (csv/pandas). Use the model only for judgment
  (rewriting titles/metas, choosing redirect targets). Never feed raw crawl rows to the model.
- `outputs/report.json` MUST match `report.schema.json`. Validate before declaring done.
- Filter to `text/html` + indexable pages before title/meta checks (see `rulebook.md`).
- Do not hard-code anything to the sample export — it must work on an unseen export.
- Keep model calls small and few (free-tier quota). One page per fix call.

## Architecture (keep it real)
- `skills/seo-audit/SKILL.md` orchestrates. Sub-agents: ingest, auditor, fixer, reporter.
- `seo/detector.py` = deterministic detectors (extend to the full rulebook — biggest score).
- `mcp/server.py` = MCP tools + the live dashboard.

## Conventions
- Commit after each working step with a real message.
- Run `python run.py sample-export/` to test end to end.

## Things I have learned during the build (update this as you go)

## 1. LLM Token Response Scrubbing

I learned that high-speed cloud reasoning models may emit:

- Raw terminal control characters (e.g., `\u001b[20D\u001b[K`)
- Internal reasoning traces (e.g., `Thinking...`)

A robust regex-based cleaning layer is required to remove this noise before saving outputs as schema-valid JSON strings.

**Key Takeaway:**
- I should always sanitize LLM responses before persistence.
- Terminal escape sequences and reasoning artifacts should be removed.
- Cleaned output should be validated against the target JSON schema.


## 2. State Initialization Sequence

I learned that the global dashboard state dictionary (`server.RUN`) must be explicitly guarded with nested dictionaries (`fixes`, `titles`, `redirect_map`) before triggering loop appends. This prevents unexpected runtime `KeyError` crashes caused by missing keys.

**Key Takeaway:**
- I should initialize all required nested structures before use.
- I should not assume dictionary keys already exist.
- Proper initialization reduces runtime failures during pipeline execution.

---

## 3. Orchestration Execution Order

I learned that all AI-driven text optimization loops and redirect mapping routines must execute and populate the shared state data model before calling:

- `server.seo_report()`
- `server.seo_export()`

Failing to do so can result in empty DataFrames being written to disk, producing incomplete or invalid reports.

**Key Takeaway:**
- Data generation must occur before reporting or exporting.
- I should ensure state population is complete before downstream processing.
- Validating shared state contents before file generation helps prevent errors.

---

## Summary

During this build, I gained three important engineering insights:

1. **Initialize shared state structures before use.**
2. **Execute data-generation workflows before reporting or exporting.**
3. **Clean and validate LLM outputs before storage.**

Applying these practices improves system reliability, report accuracy, and data integrity.