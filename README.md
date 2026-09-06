# FareBharat ✈️ — Real-time Airfare Price Index for India

**FareBharat** is an open-source platform that computes the **APIx** — a
CPI-methodology-aligned Airfare Price Index — by automatically scraping fares
from Indian airlines and OTAs, cleaning them, and publishing a daily index.

Built for **SIH 2026 · Problem Statement 26056 · MoSPI DIID**.

## Quick start (plug & play)

```powershell
cd apix
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

python demo_data.py        # 35 days of synthetic back-test data
python build_index.py      # compute daily/weekly/monthly APIx
streamlit run dashboard.py           # dashboard (http://localhost:8501)
uvicorn api:app --port 8000          # REST API (http://localhost:8000/docs)
python scheduler.py --once           # real scrape test
python scheduler.py                  # auto-run daily forever
pytest tests.py -q                   # run tests
```

API base: http://localhost:8000/docs  (key=`apix-demo-key`)

## Live deployment

FareBharat is designed for zero-cost live hosting: **GitHub Actions**
runs the scraper daily and commits fresh data; **Streamlit Cloud** serves
the public dashboard. See [`DEPLOY.md`](DEPLOY.md).

Raw quotes are saved immutably to `data/raw/` (audit trail for NSO);
logs in `logs/scraper.log`.

## Structure

```
dashboard.py                Streamlit dashboard (5 tabs, auto-refresh)
static_dashboard.html       Zero-install Chart.js fallback dashboard
api.py                      FastAPI REST endpoints
scheduler.py                Daily auto-run (fixed snapshot, CPI-style)
build_index.py              Compute APIx from cleaned quotes
demo_data.py                Seed data generator (35-day back-test)
cleaner.py                  Validation, dedup, fare decomposition, IQR outliers
index_engine.py             Jevons index, DGCA weights, weekly/monthly aggregation
db.py                       SQLite (zero config) or PostgreSQL via DATABASE_URL
scraper/base_scraper.py     Retries, backoff, UA rotation, rate-limit, raw store
scraper/easemytrip_scraper.py  Requests-based (XHR endpoint) — start here
scraper/indigo_scraper.py      Playwright DOM fallback
config/routes.yaml          Route basket + advance windows
config/weights.yaml         DGCA passenger-traffic weights + base date
tests.py                    Unit tests (pytest)
.github/workflows/scrape.yml   Daily cron scraper on GitHub Actions
```

## Adding a source

1. Open the site in Chrome, F12 → Network → Fetch/XHR, run a search.
2. Find the JSON endpoint returning fares.
3. Create `scraper/<name>_scraper.py`, extend `BaseScraper`, implement `scrape()`.
4. Register it in `scheduler.py` SCRAPERS list.

## Compliance

- Check each site's robots.txt before enabling it.
- Rate-limit 6-15s per request, daily snapshot only.
- Identifiable UA, no CAPTCHA circumvention; blocked sources are
  logged as failures and skipped, never forced.

## About the name

**FareBharat** = "Fare" (airfare) + "Bharat" (India). The platform publishes
the **APIx** — Airfare Price Index — a real-time, MoSPI-friendly counterpart
to the manual price collection currently used for the Transport
sub-group of India's Consumer Price Index.
