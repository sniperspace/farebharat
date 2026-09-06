"""Live end-to-end test: one route, one date, real Ixigo scrape -> cleaner -> DB."""
import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from cleaner import clean_quotes  # noqa: E402
from db import get_session, init_db, upsert_quotes  # noqa: E402
from scraper.ixigo_scraper import IxigoScraper  # noqa: E402

init_db()
scraper = IxigoScraper()
route = {"origin": "DEL", "dest": "BOM", "windows": [7]}
travel = (datetime.now() + timedelta(days=7)).date()

print(f"scraping DEL-BOM travel {travel} ...")
quotes = scraper.scrape(route, travel)
print(f"raw quotes: {len(quotes)}")
if quotes:
    carriers = {}
    for q in quotes:
        carriers[q["carrier"]] = min(carriers.get(q["carrier"], 1e9), q["total_fare"])
    print("cheapest per carrier:", {k: f"₹{v:,.0f}" for k, v in sorted(carriers.items(), key=lambda x: x[1])})

cleaned = clean_quotes([
    dict(q, scraped_date=datetime.now().date(), advance_window=7) for q in quotes
])
print(f"cleaned rows: {len(cleaned)}")
for r in cleaned:
    print(f"  {r['carrier']:22} ₹{r['total_fare']:>9,.0f}  base {r['base_fare']:>9,.0f}  tax {r['taxes_fees']:>8,.0f}")

n = upsert_quotes(cleaned)
print(f"inserted into DB: {n}")
