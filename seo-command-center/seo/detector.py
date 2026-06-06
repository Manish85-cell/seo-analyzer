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
    # 1. Redirect Chains Mapping
    redirect_lookup = {r["Address"]: r.get("Redirect URL", "").strip() for r in rows if 300 <= _int(r.get("Status Code")) <= 399 and r.get("Redirect URL")}
    chain_starts = []
    
    for start_url in redirect_lookup.keys():
        visited = set()
        current = start_url
        path = []
        
        while current in redirect_lookup and current not in visited:
            visited.add(current)
            path.append(current)
            current = redirect_lookup[current]
            
        if len(path) > 1:
            chain_starts.append(start_url)
            
    add("redirect_chain", "High", chain_starts, "URLs that map to a redirecting destination forming a multi-hop chain.")

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
    cmd = ["ollama", "run", "qwen3.5:9b", prompt_text]
    response = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    return response.stdout.strip()

def generating_validated_metadata_fix(url, current_bad_title, context_hint=""):
    """
    Generates alternative titles via local LLM and evaluates them against character limits
    using an automated validation loop.
    """
    base_prompt = (
        f"Optimize this webpage title tag to be compelling and descriptive. Brand: Example. "
        f"Target URL: {url}. Current Title: '{current_bad_title}'. Context: {context_hint}. "
        f"Output ONLY the raw new title string. Do not wrap in quotes or explanations."
    )
    
    suggested_title = call_local_llm_fixer(base_prompt)
    
    # Defensive Validation Loop Guardrail
    attempts = 0
    while (len(suggested_title) > 60 or len(suggested_title) < 30) and attempts < 3:
        fallback_prompt = (
            f"Your previous title recommendation was invalid because it violated length constraints ({len(suggested_title)} chars). "
            f"Rewrite the following title to be strictly between 30 and 60 characters long: '{suggested_title}'"
        )
        suggested_title = call_local_llm_fixer(fallback_prompt)
        attempts += 1
        
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

if __name__ == "__main__":
    import sys, json
    d = sys.argv[1] if len(sys.argv) > 1 else "../sample-export"
    rows = load_rows(d)
    iss = detect(rows)
    print(f"Loaded {len(rows)} rows, detected {len(iss)} issue types.")
    print(json.dumps(summarize(iss), indent=2))
    for i in iss:
        print(f"  [{i['severity']:<6}] {i['type']:<24} x{i['count']}")