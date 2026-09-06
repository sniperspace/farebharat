import json
import logging
import os
import random
import time
import urllib.robotparser
from datetime import datetime
from pathlib import Path

# CI mode: shorter delays, fewer retries so a blocked run finishes in minutes,
# not hours. Cloud IPs (GitHub Actions) are almost always blocked by airline
# sites — we still try, log the failure, then fall back to demo data.
CI_MODE = os.environ.get("FAREBHARAT_CI") == "1"

logging.basicConfig(
    filename="logs/scraper.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# robots.txt verdicts cached per host for the process lifetime
_ROBOTS_CACHE: dict = {}


def robots_allows(url: str, user_agent: str = "FareBharatBot/1.0 (+statistical research; contact: nso-moit@example.gov.in)") -> bool:
    """True if robots.txt of the host permits fetching `url` for our UA.

    Fetched via requests (urllib's default UA gets 403 from CDNs, which
    robotparser misreads as disallow-all). Cached per host; on fetch
    failure we fail-open but log, so a transient outage doesn't kill
    data collection.
    """
    import requests as _rq
    from urllib.parse import urlparse

    host = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    if host not in _ROBOTS_CACHE:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = _rq.get(f"{host}/robots.txt", timeout=30, headers={
                "User-Agent": USER_AGENTS[0],
            })
            rp.parse(r.text.splitlines())
            _ROBOTS_CACHE[host] = rp
        except Exception as exc:  # noqa: BLE001
            logging.warning("robots.txt unreachable for %s (%s) — failing open", host, exc)
            _ROBOTS_CACHE[host] = None
    rp = _ROBOTS_CACHE[host]
    if rp is None:
        return True
    try:
        return rp.can_fetch(user_agent, url)
    except Exception:  # noqa: BLE001
        return True


class BaseScraper:
    """Parent class for all source scrapers.

    Provides: retry with exponential backoff, UA rotation,
    rate-limiting, raw-response storage (audit trail).
    Subclasses must implement scrape().
    """

    name = "base"
    max_retries = 1 if CI_MODE else 3
    delay_range = (1, 2) if CI_MODE else (5, 10)  # ethical rate limit off-CI

    def run(self, route: dict, date: str) -> list:
        """Run scrape for one route+date with retries."""
        for attempt in range(1, self.max_retries + 1):
            try:
                self._polite_delay()
                quotes = self.scrape(route, date)
                if quotes is None:
                    quotes = []
                self.save_raw(route, date, quotes)
                logging.info(
                    "%s %s-%s %s -> %d quotes",
                    self.name, route["origin"], route["dest"], date, len(quotes),
                )
                return quotes
            except Exception as exc:  # noqa: BLE001
                logging.error(
                    "%s %s-%s %s attempt %d failed: %s",
                    self.name, route["origin"], route["dest"], date, attempt, exc,
                )
                # Exponential backoff — skipped in CI (cloud IPs stay blocked
                # regardless of wait time, and we have a demo-data fallback).
                if not CI_MODE:
                    time.sleep(30 * attempt)
        self.save_failure(route, date)
        return []

    def scrape(self, route: dict, date: str) -> list:
        """Subclasses implement: return list of quote dicts."""
        raise NotImplementedError

    def _polite_delay(self):
        time.sleep(random.uniform(*self.delay_range))

    @staticmethod
    def random_headers() -> dict:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/html;q=0.9",
            "Accept-Language": "en-IN,en;q=0.9",
        }

    def save_raw(self, route: dict, date: str, quotes: list):
        """Store every raw response immutably (audit trail for NSO)."""
        out_dir = Path("data/raw")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = (
            out_dir / f"{self.name}_{route['origin']}{route['dest']}"
            f"_{date}_{ts}.json"
        )
        payload = {
            "source": self.name,
            "origin": route["origin"],
            "dest": route["dest"],
            "search_date": date,
            "scraped_at": datetime.now().isoformat(),
            "quotes": quotes,
        }
        fname.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def save_failure(self, route: dict, date: str):
        out_dir = Path("logs")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = out_dir / f"failure_{self.name}_{route['origin']}{route['dest']}_{ts}.json"
        fname.write_text(
            json.dumps({"route": route, "date": date, "scraped_at": datetime.now().isoformat()}),
            encoding="utf-8",
        )
