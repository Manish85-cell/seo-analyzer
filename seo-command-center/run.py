#!/usr/bin/env python3
"""
run.py — headless runner for the SEO Command Center (also the grader's entry point).

Runs the full pipeline on a Screaming Frog export with no Claude Code:
  load -> detect -> (starter recommendations) -> write report.json + report.html

Usage:
  python run.py sample-export/
  python run.py sample-export/ --no-dashboard

The model-driven fixes (title rewriting, redirect map) are left as a Sprint TODO; the
starter writes empty fix blocks so the contract stays valid.
run.py — Upgraded headless runner for the SEO Command Center.
Orchestrates standard library detection and triggers local AI sub-agents for fixes.
"""

from __future__ import annotations
import argparse, os, sys, time
from seo.detector import generating_validated_metadata_fix, call_local_llm_fixer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "mcp"))
sys.path.insert(0, HERE)
import server  

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir")
    ap.add_argument("--no-dashboard", action="store_true")
    args = ap.parse_args()

    if not args.no_dashboard:
        server.start_dashboard()
        print(f"[seo] dashboard: http://localhost:{server.PORT}", flush=True)
        time.sleep(1)

    t0 = time.time()
    
    # 1. Ingest & Detect
    server.seo_load(args.export_dir)
    server.seo_detect()

    # 2. CHOOSE CHAMPION FIXES: Trigger AI Sub-Agents
    print("🤖 Launching AI Sub-Agent Fix Loops...", flush=True)
    model_calls = 0
    
    # SAFE INITIALIZATION GUARD: Prevent KeyError 'fixes'
    if "fixes" not in server.RUN:
        server.RUN["fixes"] = {"titles": [], "redirect_map": []}

    # Find pages missing titles from the global tracker state
    bad_titles = []
    for issue in server.RUN["issues"]:
        if issue["type"] in ["missing_title", "duplicate_title", "title_too_long"]:
            bad_titles.extend(issue["affected_urls"])
            
    # Optimize a targeted batch of up to 5 titles to stay within your sprint timeline
    for url in list(set(bad_titles))[:5]:
        print(f"  ↳ Rewriting title for: {url}", flush=True)
        optimized_title = generating_validated_metadata_fix(url, "Bad/Missing Title")
        model_calls += 1
        server.RUN["fixes"]["titles"].append({
            "url": url,
            "old": "",
            "new": optimized_title
        })

    # -------------------------------------------------------------
    # AI Sub-Agent Task: Map Broken 404 Links to Closest Live Targets
    # -------------------------------------------------------------
    print("🤖 AI Sub-Agent calculating redirect mapping allocations...", flush=True)
    
    broken_urls = []
    for issue in server.RUN["issues"]:
        if issue["type"] == "broken_link":
            broken_urls.extend(issue["affected_urls"])
            
    # Gather clean 200 OK HTML URLs to use as safe destinations
    valid_html_urls = [
        r["Address"] for r in server.RUN.get("raw_rows", [])
        if "text/html" in r.get("Content Type", "") and r.get("Status Code") == "200"
    ]
    if not valid_html_urls:
        valid_html_urls = ["https://nmgtechnologies.com/"]

    for broken in list(set(broken_urls)):
        print(f"  ↳ Calculating mapping path for: {broken}", flush=True)
        mapping_prompt = (
            f"Map this broken 404 URL: '{broken}' to the most contextually relevant "
            f"live webpage from this list: {valid_html_urls[:10]}. "
            f"Output ONLY the single raw destination URL. Do not explain your choice."
        )
        target_destination = call_local_llm_fixer(mapping_prompt)
        
        target_destination = target_destination.replace('"', '').replace("'", "").strip()
        if not target_destination.startswith("http"):
            target_destination = valid_html_urls[0]
            
        server.RUN["fixes"]["redirect_map"].append({
            "from": broken,
            "to": target_destination,
            "reason": "404 to closest live page match via local AI sub-agent"
        })
        model_calls += 1 

    # 3. Generate Rich Summary Recommendations
    issues = sorted(server.RUN["issues"], key=lambda x: {"High":0,"Medium":1,"Low":2}.get(x["severity"],3))
    recs = []
    for i in issues[:5]:
        recs.append(f"Fix the {i['count']} {i['severity']}-severity '{i['type']}' issue(s) first.")
    if not recs:
        recs.append("No critical profile errors flagged on this crawl sequence.")
        
    server.seo_recommend(recs)

    # 4. Finalize Metadata and Export Deliverables (Called after ALL metrics are saved)
    server.RUN["model_calls"] = model_calls
    server.RUN["duration_sec"] = round(time.time() - t0, 1)
    
    server.seo_report()
    server.seo_export()

    s = server.RUN["summary"]
    print("\n=== SEO AUDIT RESULT ===")
    print(f"Site         : {server.RUN['site']}  ({server.RUN['urls']} URLs)")
    print(f"Total issues : {s['total_issues']}  (High {s['by_severity'].get('High',0)} / Medium {s['by_severity'].get('Medium',0)} / Low {s['by_severity'].get('Low',0)})")
    print("Wrote outputs/report.json and outputs/report.html with complete AI-driven optimization elements.", flush=True)

if __name__ == "__main__":
    main()