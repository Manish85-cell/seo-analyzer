"""
detector.py — deterministic SEO issue detection from a Screaming Frog internal_all.csv.

STARTER IMPLEMENTATION. It already detects several issues so the pipeline runs end to
end. Your job in the Sprint is to COMPLETE the rulebook (see rulebook.md): add the
missing detectors, handle edge cases, and improve accuracy against the hidden export.

Standard library only (csv). Detection is plain Python on purpose — the model is for
judgment (rewriting titles, choosing redirect targets), not for counting rows.
"""

from __future__ import annotations
import csv
import os
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


def is_html(r):  return "text/html" in (r.get("Content Type", "") or "").lower()
def is_200(r):   return _int(r.get("Status Code")) == 200
def indexable(r): return (r.get("Indexability", "") or "").strip().lower() == "indexable"


def detect(rows: list[dict]) -> list[dict]:
    """Return a list of issue dicts: {type, severity, affected_urls, count, explanation}.
    STARTER set — extend to the full rulebook for a high score."""
    issues = []

    def add(t, sev, urls, explanation):
        urls = sorted(set(urls))
        if urls:
            issues.append({"type": t, "severity": sev, "affected_urls": urls,
                           "count": len(urls), "explanation": explanation})

    html = [r for r in rows if is_html(r)]
    idx200 = [r for r in html if is_200(r) and indexable(r)]

    # --- Titles ---
    add("missing_title", "High",
        [r["Address"] for r in idx200 if not (r.get("Title 1", "") or "").strip()],
        "Indexable pages with no title tag.")

    # duplicate titles (indexable only)
    by_title = defaultdict(list)
    for r in idx200:
        t = (r.get("Title 1", "") or "").strip()
        if t:
            by_title[t].append(r["Address"])
    dup_t = [u for urls in by_title.values() if len(urls) > 1 for u in urls]
    add("duplicate_title", "High", dup_t, "Pages sharing an identical title.")

    add("title_too_long", "Medium",
        [r["Address"] for r in idx200
         if _int(r.get("Title 1 Pixel Width")) > 561 or _int(r.get("Title 1 Length")) > 60],
        "Titles likely truncated in search results.")

    # --- Response codes ---
    add("broken_link", "High",
        [r["Address"] for r in rows if 400 <= _int(r.get("Status Code")) <= 499],
        "URLs returning a client error (4xx).")
    add("server_error", "High",
        [r["Address"] for r in rows if 500 <= _int(r.get("Status Code")) <= 599],
        "URLs returning a server error (5xx).")
    add("redirect", "Medium",
        [r["Address"] for r in rows if 300 <= _int(r.get("Status Code")) <= 399],
        "URLs that redirect (3xx).")

    # --- Orphan pages ---
    add("orphan_page", "Medium",
        [r["Address"] for r in idx200 if _int(r.get("Inlinks")) == 0],
        "Indexable pages with zero internal links in.")

    # ----------------------------------------------------------------------- #
    # TODO (Sprint): add the rest of the rulebook for full accuracy:
    #   title_too_short, missing_meta_description, duplicate_meta_description,
    #   meta_description_too_long, missing_h1, duplicate_h1, redirect_chain,
    #   thin_content, non_indexable_but_linked, slow_page
    # Each is a short rule over the columns — see rulebook.md.
    # ----------------------------------------------------------------------- #

    return issues

import pandas as pd
import json
import os

def ingest_screaming_frog_data(export_dir_path):
    """
    Stage 1: Safely handles character encoding variations and commas within quotes
    to import the master crawl dataframe.
    """
    master_file_path = os.path.join(export_dir_path, "internal_all.csv")
    
    if not os.path.exists(master_file_path):
        raise FileNotFoundError(f"Critical input missing: {master_file_path}")
        
    # Read using UTF-8 handling to prevent crash-failures on special characters
    df = pd.read_csv(master_file_path, encoding='utf-8', low_memory=False)
    
    # Clean whitespace strings from header elements
    df.columns = df.columns.str.strip()
    
    total_urls = len(df)
    print(f"[TELEMETRY] Stage 1 Ingest Complete. Successfully loaded {total_urls} URLs.")
    
    return df, total_urls

def audit_page_titles(df):
    """
    Feature 2.1: Validates Title lengths, structural omissions, and cross-page duplication.
    Rulebook constraints: Length (30-60 chars), Width (max 561px).
    """
    # Defensive Filter: Only analyze active, indexable HTML documents for Title standards
    html_mask = (df['Content Type'].str.contains('text/html', na=False)) & \
                (df['Indexability'] == 'Indexable') & \
                (df['Status Code'] == 200)
    
    target_df = df[html_mask]
    
    # 1. Missing Titles
    missing_titles = target_df[target_df['Title 1'].isna() | (target_df['Title 1'].str.strip() == '')]
    
    # 2. Duplicate Titles
    duplicate_titles = target_df[target_df.duplicated(subset=['Title 1'], keep=False) & target_df['Title 1'].notna()]
    
    # 3. Title Over Max Length Thresholds (> 60 Chars OR > 561 Pixels)
    too_long_titles = target_df[
        (target_df['Title 1 Length'] > 60) | 
        (target_df['Title 1 Pixel Width'] > 561)
    ]
    
    # 4. Title Under Min Length (< 30 Chars)
    too_short_titles = target_df[target_df['Title 1 Length'] < 30]
    
    return {
        "missing": missing_titles['Address'].tolist(),
        "duplicate": duplicate_titles['Address'].tolist(),
        "too_long": too_long_titles['Address'].tolist(),
        "too_short": too_short_titles['Address'].tolist()
    }

def audit_meta_descriptions(df):
    """
    Feature 2.2: Evaluates Meta Description structural metrics on indexable HTML assets.
    """
    html_mask = (df['Content Type'].str.contains('text/html', na=False)) & \
                (df['Indexability'] == 'Indexable') & \
                (df['Status Code'] == 200)
    
    target_df = df[html_mask]
    
    missing_metas = target_df[target_df['Meta Description 1'].isna() | (target_df['Meta Description 1'].str.strip() == '')]
    duplicate_metas = target_df[target_df.duplicated(subset=['Meta Description 1'], keep=False) & target_df['Meta Description 1'].notna()]
    too_long_metas = target_df[target_df['Meta Description 1Length'] > 155]
    
    return {
        "missing": missing_metas['Address'].tolist(),
        "duplicate": duplicate_metas['Address'].tolist(),
        "too_long": too_long_metas['Address'].tolist()
    }

def audit_structural_and_server(df):
    """
    Feature 2.3: Tracks core HTTP statuses and basic header elements across all crawled entries.
    """
    results = {
        "missing_h1": df[(df['Status Code'] == 200) & (df['H1-1'].isna() | (df['H1-1'].str.strip() == ''))]['Address'].tolist(),
        "broken_links_4xx": df[(df['Status Code'] >= 400) & (df['Status Code'] < 500)]['Address'].tolist(),
        "server_errors_5xx": df[(df['Status Code'] >= 500) & (df['Status Code'] < 600)]['Address'].tolist(),
        "redirects_3xx": df[(df['Status Code'] >= 300) & (df['Status Code'] < 400)]['Address'].tolist()
    }
    return results

def audit_relational_structures(df):
    """
    Feature 2.4: Evaluates linkages and multi-hop routing paths.
    """
    # 1. Redirect Chains Mapping
    redirect_lookup = df[df['Redirect URL'].notna()].set_index('Address')['Redirect URL'].to_dict()
    chains = []
    
    for start_url in redirect_lookup.keys():
        visited = set()
        current = start_url
        path = []
        
        while current in redirect_lookup and current not in visited:
            visited.add(current)
            path.append(current)
            current = redirect_lookup[current]
            
        if len(path) > 1:  # Indicates a multi-hop destination chain
            chains.append(path[0])
            
    # 2. Orphan Pages (0 internal structural incoming references)
    orphan_pages = df[(df['Status Code'] == 200) & 
                      (df['Indexability'] == 'Indexable') & 
                      (df['Inlinks'] == 0)]['Address'].tolist()
                      
    return {
        "redirect_chains": chains,
        "orphan_pages": orphan_pages
    }

def summarize(issues: list[dict]) -> dict:
    by_sev = defaultdict(int)
    for i in issues:
        by_sev[i["severity"]] += 1
    return {"total_issues": len(issues),
            "by_severity": {"High": by_sev["High"], "Medium": by_sev["Medium"], "Low": by_sev["Low"]}}


if __name__ == "__main__":
    import sys, json
    d = sys.argv[1] if len(sys.argv) > 1 else "../sample-export"
    rows = load_rows(d)
    iss = detect(rows)
    print(f"Loaded {len(rows)} rows, detected {len(iss)} issue types.")
    print(json.dumps(summarize(iss), indent=2))
    for i in iss:
        print(f"  [{i['severity']:<6}] {i['type']:<24} x{i['count']}")
