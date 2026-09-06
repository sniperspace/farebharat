"""Endpoint discovery probe — runs on GitHub Actions or locally.

Opens real search pages in headless Chromium, captures every
fare-bearing JSON/XHR response, saves results + screenshots.

Usage:
    python probe/discover.py            # uses default route DEL->BOM T+7
    FARE_PROBE_SITE=easemytrip python probe/discover.py   # one site only

Standalone by design (no repo imports) so it can also run in Colab.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

OUT = Path("probe")
OUT.mkdir(exist_ok=True)
(OUT / "screenshots").mkdir(exist_ok=True)

ORIGIN = os.environ.get("FARE_PROBE_ORIGIN", "DEL")
DEST = os.environ.get("FARE_PROBE_DEST", "BOM")
T_PLUS = int(os.environ.get("FARE_PROBE_TPLUS", "7"))
ONLY_SITE = os.environ.get("FARE_PROBE_SITE", "").lower()

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

FARE_KEY_RE = re.compile(r"(fare|price|amount|total)", re.I)
FARE_TEXT_RE = re.compile(r"(?:₹|INR\s?)\s?\d{1,2},?\d{3}")


def travel_date(fmt: str) -> str:
    d = datetime.now() + timedelta(days=T_PLUS)
    return d.strftime(fmt)


def sites() -> dict:
    return {
        "easemytrip": [
            (
                "search",
                "https://www.easemytrip.com/flights.html?SearchType=O&Org="
                f"{ORIGIN}&Dest={DEST}&DT={travel_date('%d/%m/%Y')}&RT=&PC=0&CL=E&Fnc=0&AF=0&TF=0&AR=Any",
            ),
            ("home", "https://www.easemytrip.com/flights.html"),
        ],
        "ixigo": [
            (
                "search",
                f"https://www.ixigo.com/search/result/flight/{ORIGIN}/{DEST}/"
                f"{travel_date('%d%m%y')}//1/0/0/E",
            ),
            ("home", "https://www.ixigo.com/flights"),
        ],
        "indigo": [
            (
                "search",
                f"https://www.goindigo.in/flight-booking/select-flight.html"
                f"?Origin={ORIGIN}&Destination={DEST}&TripType=O&DepartureDate={travel_date('%Y-%m-%d')}",
            ),
        ],
    }


def part1_http_sanity(results: dict):
    """Can the runner reach these hosts at all (network-level)?"""
    print("\n=== PART 1: HTTP reachability ===")
    results["http_sanity"] = {}
    for name in ("easemytrip", "ixigo", "goindigo"):
        host = f"https://www.{name}.com"
        entry = {}
        try:
            r = requests.get(
                host,
                headers={"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"},
                timeout=30,
            )
            entry["status"] = r.status_code
            entry["server"] = r.headers.get("server", "")
            entry["len"] = len(r.text)
            low = r.text[:20000].lower()
            entry["captcha_signals"] = [
                w for w in ("captcha", "access denied", "blocked", "pardon our interruption", "verify you are human")
                if w in low
            ]
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {exc}"
        results["http_sanity"][name] = entry
        print(f"{name:12} -> {entry}")


def walk_keys(node, hits: list, path: str = ""):
    """Collect (path, value) for fare-like keys in nested JSON."""
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}"
            if FARE_KEY_RE.search(str(k)) and isinstance(v, (int, float, str)) and re.search(r"\d", str(v)):
                hits.append((p, str(v)[:40]))
            walk_keys(v, hits, p)
    elif isinstance(node, list):
        for i, v in enumerate(node[:3]):
            walk_keys(v, hits, f"{path}[{i}]")


def part2_browser(results: dict):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n=== PART 2 SKIPPED: playwright not installed on this host ===")
        results["browser"] = {"error": "playwright not installed"}
        return

    print("\n=== PART 2: Playwright browser capture ===")
    results["browser"] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        ctx = browser.new_context(
            user_agent=UA,
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1366, "height": 768},
        )

        for site, attempts in sites().items():
            if ONLY_SITE and site != ONLY_SITE:
                continue
            site_res = []
            for label, url in attempts:
                page = ctx.new_page()
                captured = []
                requests_log = []

                def on_request(req, _log=requests_log):
                    try:
                        u = req.url.lower()
                        if any(k in u for k in ("api", "search", "fare", "flight", "availability")):
                            _log.append({
                                "method": req.method,
                                "url": req.url[:300],
                                "post_data": (req.post_data or "")[:400] if req.method == "POST" else None,
                                "headers": {
                                    k: v for k, v in list(req.headers.items())[:12]
                                    if k.lower() in ("content-type", "origin", "referer", "x-requested-with")
                                },
                            })
                    except Exception:  # noqa: BLE001
                        pass

                def on_response(resp, _captured=captured):
                    try:
                        ctype = resp.headers.get("content-type", "")
                        u = resp.url
                        same_site_json = (
                            "json" in ctype
                            and any(h in u for h in ("easemytrip.", "ixigo.", "edge.ixigo", "goindigo."))
                        )
                        interesting = (
                            same_site_json
                            or any(k in u.lower() for k in ("api", "fare", "search", "flight", "availability"))
                        )
                        if not interesting or resp.status != 200:
                            return
                        body = resp.text()
                        if not body or len(body) < 50:
                            return
                        fare_hits = []
                        if "json" in ctype:
                            try:
                                walk_keys(json.loads(body), fare_hits)
                            except Exception:  # noqa: BLE001
                                pass
                        if not (fare_hits or FARE_TEXT_RE.search(body[:20000]) or same_site_json):
                            return
                        _captured.append({
                            "url": u[:300],
                            "status": resp.status,
                            "ctype": ctype,
                            "len": len(body),
                            "fare_keys": fare_hits[:8],
                            "snippet": body[:250],
                        })
                    except Exception:  # noqa: BLE001
                        pass

                page.on("response", on_response)
                page.on("request", on_request)
                entry = {"url": url, "final_url": "", "title": "", "block_signals": []}
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(4000)
                    if site == "easemytrip" and label == "search":
                        # submit the search form in-page; site navigates to results
                        try:
                            page.evaluate(
                                f"FlightSearch('{ORIGIN}','{DEST}','{travel_date('%d/%m/%Y')}')"
                            )
                        except Exception:
                            try:
                                page.click("input.srchBtnSe", timeout=5000)
                            except Exception:  # noqa: BLE001
                                pass
                        page.wait_for_load_state("domcontentloaded", timeout=45000)
                    if site == "ixigo" and label == "search":
                        # Next.js app: fare API fires after a longer settle
                        page.wait_for_timeout(25000)
                    page.wait_for_timeout(6000)
                    # trigger lazy XHRs
                    for _ in range(4):
                        page.mouse.wheel(0, 900)
                        page.wait_for_timeout(2500)
                    entry["final_url"] = page.url[:300]
                    entry["title"] = page.title()[:120]
                    low = (page.content() or "")[:30000].lower()
                    entry["block_signals"] = [
                        w for w in ("access denied", "blocked", "verify you are human")
                        if w in low
                    ]
                    # DOM fare extraction: prove fares visible to a real browser
                    dom_fares = page.eval_on_selector_all(
                        "body",
                        """el => {
                            const t = el.innerText || '';
                            const m = t.match(/(?:\\u20B9|INR\\s?)\\s?\\d{1,2},?\\d{3}/g) || [];
                            return m.slice(0, 15);
                        }""",
                    )
                    entry["dom_fares"] = dom_fares
                    entry["dom_fare_count"] = len(dom_fares)
                except Exception as exc:  # noqa: BLE001
                    entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
                entry["captured"] = captured
                entry["requests"] = requests_log[:40]
                shot = OUT / "screenshots" / f"{site}_{label}.png"
                try:
                    page.screenshot(path=str(shot), full_page=False)
                    entry["screenshot"] = str(shot)
                except Exception:  # noqa: BLE001
                    pass
                page.close()
                site_res.append(entry)
                print(f"[{site}/{label}] captured={len(captured)} "
                      f"block_signals={entry.get('block_signals')} title={entry.get('title')!r}")
                if captured:
                    for c in captured[:5]:
                        print(f"    -> {c['url']}")
                if requests_log:
                    print(f"    requests tracked: {len(requests_log)}")
                    for r in requests_log[:10]:
                        m = r.get("post_data")
                        print(f"    [{r['method']}] {r['url']}" + (f"  POST={m[:120]!r}" if m else ""))
                if entry.get("dom_fare_count"):
                    print(f"    DOM fares visible: {entry['dom_fare_count']} e.g. {entry['dom_fares'][:5]}")
            results["browser"][site] = site_res

        browser.close()


def main():
    results = {"meta": {
        "route": f"{ORIGIN}-{DEST}", "t_plus": T_PLUS,
        "ran_at": datetime.now().isoformat(),
        "runner": "github-actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "local",
    }}
    part1_http_sanity(results)
    part2_browser(results)
    out_file = OUT / "discovery_results.json"
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved {out_file}")

    print("\n=== SUMMARY ===")
    for site, entries in results.get("browser", {}).items():
        if not isinstance(entries, list):
            print(f"{site:12} : SKIPPED ({entries})")
            continue
        best = max((len(e.get("captured", [])) for e in entries), default=0)
        verdict = "FARE DATA CAPTURED" if best else "NO FARE DATA"
        print(f"{site:12} : {verdict} ({best} responses)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
