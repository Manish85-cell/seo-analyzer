# PROMPTS.md — Key Agentic Prompts

This log tracks the prompts that drove the SEO Command Center's AI fixes and the iterations required to reach production-grade output.

## 1. /.claud not in root issue / audit.jsonl not building
**Purpose**
fix the audit.json file not building issue

**Prompt**
 Why this file is not building .claude/hooks/ + audit.sh    Pre-wired audit hooks that record your build process to .claude/audit.jsonl (see section 08 — this is graded). as this is graded part help me figure out



## 2. Metadata Optimizer (Titles)
**Purpose**: Rewrite missing, too-short, or too-long page titles.

**Prompt**:
> Optimize this webpage title tag to be compelling and descriptive. Brand: NMG Technologies.
> Target URL: {url}. Current Title: '{current_bad_title}'.
> Output ONLY the raw new title string. Do not wrap in quotes, do not show your thinking, and do not include explanations.

**Iteration Note**: Initial responses often included conversational filler ("Here is the optimized title:"). Added the "Output ONLY the raw new title string" constraint and a post-processing `clean_ai_response` regex to strip artifacts.

---

## 3. Length Validation Guardrail
**Purpose**: Force the model to adhere to the 30-60 character limit when the first attempt fails.

**Prompt**:
> Your previous title was invalid. Rewrite the following topic into a clean title
> strictly between 30 and 60 characters. Return ONLY the raw text: '{suggested_title}'

**Iteration Note**: Integrated into a `while` loop in `detector.py` with a max of 2 attempts before falling back to a programmatic slug-based title.

---

## 4. Redirect Map Champion
**Purpose**: Map broken 404s to the most relevant live 200 OK pages.

**Prompt**:
> Map this broken 404 URL: '{broken}' to the most contextually relevant
> live webpage from this list: {valid_html_urls[:10]}.
> Output ONLY the single raw destination URL. Do not explain your choice.

**Iteration Note**: Limited the candidate list to the top 10 most relevant pages to avoid context window overflow and maintain model precision.


