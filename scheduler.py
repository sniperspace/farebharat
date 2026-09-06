"""Scheduler — runs all scrapers daily at a fixed time with jitter.

CPI-style: fixed daily snapshot at 06:00 IST +/- random 20 min.

Usage:
    python scheduler.py --once    # single run (good for cron / GitHub Actions)
    python scheduler.py           # loop mode (runs forever on a server)
"""

import argparse
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from scraper.base_scraper import logging
from scraper.ixigo_scraper import IxigoScraper

import os

# Ixigo is the working real source (pure-requests, see scraper/ixigo_scraper.py).
# EMT (session-bound) and IndiGo (Akamai-blocked from cloud) stay opt-in via env.
SCRAPERS = [IxigoScraper()]
if os.environ.get("FAREBHARAT_SOURCES", "").lower() in ("all", "emt,indigo"):
    from scraper.easemytrip_scraper import EaseMyTripScraper
    from scraper.indigo_scraper import IndigoScraper

    SCRAPERS += [EaseMyTripScraper(), IndigoScraper()]


def load_routes() -> list:
    with open("config/routes.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["routes"]


def compute_dates(windows: list) -> list:
    """Return dates for advance-purchase windows T+n (YYYY-MM-DD)."""
    today = datetime.now().date()
    return [(today + timedelta(days=n)).isoformat() for n in windows]


def daily_job():
    from cleaner import clean_quotes
    from db import upsert_quotes

    routes = load_routes()
    today = datetime.now().date()
    total_raw = total_new = 0
    for route in routes:
        for date in compute_dates(route["windows"]):
            travel = date if not isinstance(date, str) else datetime.fromisoformat(date).date()
            window = (travel - today).days
            for scraper in SCRAPERS:
                quotes = scraper.run(route, date)
                if not quotes:
                    continue
                total_raw += len(quotes)
                for q in quotes:
                    q.setdefault("scraped_date", today)
                    q.setdefault("advance_window", window)
                    q.setdefault("travel_date", travel.isoformat())
                cleaned = clean_quotes(quotes)
                total_new += upsert_quotes(cleaned)
    logging.info(
        "daily_job complete at %s (raw=%d, inserted=%d)",
        datetime.now().isoformat(), total_raw, total_new,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run once and exit")
    args = parser.parse_args()

    if args.once:
        daily_job()
        return

    import schedule

    # jitter: 06:00 IST +/- 20 min, avoids bot-like fixed pattern
    run_at = f"06:{random.randint(0, 20):02d}"

    def job_with_jitter():
        time.sleep(random.uniform(0, 600))
        daily_job()

    schedule.every().day.at(run_at).do(job_with_jitter)
    print(f"Scheduler started; next run at {run_at} (with jitter)")
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    Path("logs").mkdir(exist_ok=True)
    main()
