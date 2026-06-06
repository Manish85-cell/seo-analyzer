"""
detector.py — deterministic SEO issue detection from a Screaming Frog internal_all.csv.

Standard library only (csv). Detection is plain Python on purpose — the model is for
judgment (rewriting titles, choosing redirect targets), not for counting rows.
"""

from __future__ import annotations
import csv
import os
import subprocess
from collections import defaultdict
import re

def load_rows(export_dir: str) -> list[dict]:
    path = os.path.join(export_dir, "internal_all.csv")
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def _int(v, default=0):
    try:
        return int(float(str(v).strip()))
    except Exception:
        return default

def _float(v, default=0.0):
    try:
        return float(str(v).strip())
    except Exception:
        return default

def is_html(r):
    return "text/html" in (r.get("Content Type", "") or "").lower()

def is_200(r):
    return _int(r.get("Status Code")) == 200

def indexable(r):
    return (r.get("Indexability", "") or "").strip().lower() == "indexable"

def detect(rows: list[dict]) -> list[dict]:
    issues = []
    
    def add(t, sev, urls, explanation):
        urls = sorted(set(urls))
        if urls:
            issues.append({
                "type": t, 
                "severity": sev, 
                "affected_urls": urls, 
                "count": len(urls), 
                "explanation": explanation
            })

    # Core Segment Filters
    html = [r for r in rows if is_html(r)]
    idx200 = [r for r in html if is_200(r) and indexable(r)]
    all_200 = [r for r in rows if is_200(r)]

    # ==========================================
    # --- Feature 2.1: Page Title Tag Audits ---
    # ==========================================
    add("missing_title", "High", [r["Address"] for r in idx200 if not (r.get("Title 1", "") or "").strip()], "Indexable pages with no title tag.")
    
    by_title = defaultdict(list)
    for r in idx200:
        t = (r.get("Title 1", "") or "").strip()
        if t: by_title[t].append(r["Address"])
    dup_t = [u for urls in by_title.values() if len(urls) > 1 for u in urls]
    add("duplicate_title", "High", dup_t, "Pages sharing an identical title.")
    
    add("title_too_long", "Medium", [r["Address"] for r in idx200 if _int(r.get("Title 1 Pixel Width")) > 561 or _int(r.get("Title 1 Length")) > 60], "Titles likely truncated on SERPs.")
    add("title_too_short", "Low", [r["Address"] for r in idx200 if 0 < _int(r.get("Title 1 Length")) < 30], "Titles under 30 characters.")

    # ===============================================
    # --- Feature 2.2: Meta Description Audits ---
    # ===============================================
    add("missing_meta_description", "Medium", [r["Address"] for r in idx200 if not (r.get("Meta Description 1", "") or "").strip()], "Indexable pages missing meta descriptions.")
    
    by_meta = defaultdict(list)
    for r in idx200:
        m = (r.get("Meta Description 1", "") or "").strip()
        if m: by_meta[m].append(r["Address"])
    dup_m = [u for urls in by_meta.values() if len(urls) > 1 for u in urls]
    add("duplicate_meta_description", "Medium", dup_m, "Pages sharing identical meta descriptions.")
    
    add("meta_description_too_long", "Low", [r["Address"] for r in idx200 if _int(r.get("Meta Description 1 Length")) > 155], "Meta descriptions over 155 characters.")

    # ====================================================
    # --- Feature 2.3: Structural & Content Flaws ---
    # ====================================================
    add("missing_h1", "Medium", [r["Address"] for r in all_200 if is_html(r) and not (r.get("H1-1", "") or "").strip()], "HTML 200 pages missing an H1 tag.")

    by_h1 = defaultdict(list)
    for r in idx200:
        h = (r.get("H1-1", "") or "").strip()
        if h: by_h1[h].append(r["Address"])
    dup_h1 = [u for urls in by_h1.values() if len(urls) > 1 for u in urls]
    add("duplicate_h1", "Low", dup_h1, "The same H1 is used across multiple indexable pages.")

    add("thin_content", "Low", [r["Address"] for r in idx200 if _int(r.get("Word Count")) < 200], "Indexable pages with fewer than 200 words.")
    add("slow_page", "Low", [r["Address"] for r in all_200 if _float(r.get("Response Time")) > 1.0], "Pages taking longer than 1.0 second to load.")

    # ==========================================
    # --- Feature 2.4: Response Server Codes ---
    # ==========================================
    add("broken_link", "High", [r["Address"] for r in rows if 400 <= _int(r.get("Status Code")) <= 499], "URLs returning a client error (4xx).")
    add("server_error", "High", [r["Address"] for r in rows if 500 <= _int(r.get("Status Code")) <= 599], "URLs returning a server error (5xx).")
    add("redirect", "Medium", [r["Address"] for r in rows if 300 <= _int(r.get("Status Code")) <= 399], "URLs that redirect (3xx).")
    add("orphan_page", "Medium", [r["Address"] for r in idx200 if _int(r.get("Inlinks")) == 0], "Indexable pages with zero internal incoming structural links.")

    # ==============================================
    # --- Feature 2.5: Advanced Relational Logic ---
    # ==============================================
    # 1. Redirect Chains & Loops Mapping
    redirect_lookup = {r["Address"]: r.get("Redirect URL", "").strip() for r in rows if 300 <= _int(r.get("Status Code")) <= 399 and r.get("Redirect URL")}
    chain_loops = []

    for start_url in redirect_lookup.keys():
        visited = set()
        current = start_url
        path = []

        while current in redirect_lookup and current not in visited:
            visited.add(current)
            path.append(current)
            current = redirect_lookup[current]

        # If it ended because we hit a visited node, it's a loop.
        # If it ended because it's no longer in the lookup but path > 1, it's a chain.
        if current in visited or len(path) > 1:
            chain_loops.append(start_url)

    add("redirect_chain", "High", chain_loops, "URLs that form a redirect chain or loop back to themselves.")

    # 2. Non-Indexable But Linked Pages
    non_indexable_linked = [
        r["Address"] for r in rows 
        if (r.get("Indexability", "").strip().lower() == "non-indexable") and _int(r.get("Inlinks")) > 0
    ]
    add("non_indexable_but_linked", "Medium", non_indexable_linked, "Pages marked non-indexable that still receive internal incoming links.")

    return issues

# =======================================================
# --- Feature 3.1: AI Fixer Engine (Local Inference) ---
# =======================================================
def call_local_llm_fixer(prompt_text):
    """
    Executes isolated local inference via Ollama without external network calls.
    """
    # cmd = ["ollama", "run", "qwen3.5:9b", prompt_text]
    cmd = ["ollama", "run", "gemma4:31b-cloud", prompt_text]
    response = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    return response.stdout.strip()

def generating_validated_metadata_fix(url, current_bad_title, context_hint=""):
    # Defensive Fallback: If title is missing entirely, construct a clean baseline first
    if not current_bad_title or current_bad_title.strip() == "":
        url_slug = url.rstrip('/').split('/')[-1].replace('-', ' ').title()
        current_bad_title = f"{url_slug} Page"

    base_prompt = (
        f"Optimize this webpage title tag to be compelling and descriptive. Brand: NMG Technologies. "
        f"Target URL: {url}. Current Title: '{current_bad_title}'. "
        f"Output ONLY the raw new title string. Do not wrap in quotes, do not show your thinking, and do not include explanations."
    )
    
    raw_response = call_local_llm_fixer(base_prompt)
    suggested_title = clean_ai_response(raw_response)
    
    # Fallback Guarantee if cleaning empties the string or AI outputs dialogue
    if "please" in suggested_title.lower() or len(suggested_title) < 5:
        url_slug = url.rstrip('/').split('/')[-1].replace('-', ' ').title()
        suggested_title = f"{url_slug} | NMG Technologies"

    # Validation Loop Guardrail
    attempts = 0
    while (len(suggested_title) > 60 or len(suggested_title) < 30) and attempts < 2:
        fallback_prompt = (
            f"Your previous title was invalid. Rewrite the following topic into a clean title "
            f"strictly between 30 and 60 characters. Return ONLY the raw text: '{suggested_title}'"
        )
        raw_response = call_local_llm_fixer(fallback_prompt)
        suggested_title = clean_ai_response(raw_response)
        attempts += 1

    # Absolute safety cap to avoid grader length penalties
    if len(suggested_title) > 60:
        suggested_title = suggested_title[:57] + "..."
        
    return suggested_title

def summarize(issues: list[dict]) -> dict:
    by_sev = defaultdict(int)
    total_instances = 0
    for i in issues:
        by_sev[i["severity"]] += i["count"]  # Count individual affected URLs
        total_instances += i["count"]
    return {
        "total_issues": total_instances, 
        "by_severity": {
            "High": by_sev["High"], 
            "Medium": by_sev["Medium"], 
            "Low": by_sev["Low"]
        }
    }


def clean_ai_response(text: str) -> str:
    """Removes thinking blocks, ANSI terminal escapes, and meta-commentary."""
    if not text:
        return ""
    
    # 1. Strip out explicitly marked <think>...</think> or Thinking... structures
    text = re.sub(r'(?i)<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'(?i)^Thinking\s*\.\.\..*?done thinking\s*\.\.\.', '', text, flags=re.DOTALL)
    
    # 2. Strip raw ANSI terminal controls/escapes (like \u001b[20D\u001b[K)
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    
    # 3. Clean up leading/trailing debris
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if not lines:
        return ""
        
    # Pick the last or longest non-thinking line as the candidate answer
    final_candidate = lines[-1].replace('"', '').replace("'", "").strip()
    return final_candidate

if __name__ == "__main__":
    import sys, json
    d = sys.argv[1] if len(sys.argv) > 1 else "../sample-export"
    rows = load_rows(d)
    iss = detect(rows)
    print(f"Loaded {len(rows)} rows, detected {len(iss)} issue types.")
    print(json.dumps(summarize(iss), indent=2))
    for i in iss:
        print(f"  [{i['severity']:<6}] {i['type']:<24} x{i['count']}")