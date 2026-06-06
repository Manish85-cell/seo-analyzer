# DECISIONS.md — Engineering Log

## [2026-06-06] Architecture: Deterministic Detection vs. AI Judgment
**Decision**: Use plain Python for issue detection and LLMs only for generating fixes.
**Reasoning**: The SEO rulebook is based on hard thresholds (e.g., Pixel Width > 561). Using an LLM to count characters or detect empty strings is unreliable and slow. This separation ensures 100% accuracy in detection.

## [2026-06-06] Model Pivot: Local to Cloud (Ollama)
**Decision**: Shifted execution from purely local processing to `gemma4:31b-cloud` via Ollama.
**Reasoning**: Local inference on a MacBook Air was taking 15+ minutes. The cloud-backed Ollama model reduced the total pipeline runtime to 84.4 seconds without sacrificing fix quality.

## [2026-06-06] Response Sanitization Layer
**Decision**: Implemented `clean_ai_response` using regex to strip `<think>` blocks and ANSI escape codes.
**Reasoning**: The reasoning models were leaking internal thoughts and terminal control characters into the `report.json`, which violated the schema and corrupted the HTML output.

## [2026-06-06] State Management Guard
**Decision**: Explicitly initialize `server.RUN["fixes"]` in `run.py` before AI loops start.
**Reasoning**: Prevented intermittent `KeyError` crashes when the AI agent attempted to append results to a dictionary key that hadn't been created yet.

## [2026-06-06] Export Sequencing
**Decision**: Shifted `seo_report()` and `seo_export()` to the absolute end of the `main()` loop in `run.py`.
**Reasoning**: Fixed a bug where reports were being written before the AI sub-agents had finished generating the fix mappings.
