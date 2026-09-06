"""IndiGo scraper using Playwright (JS-rendered pages).

Prefer the XHR/JSON approach when the endpoint is identified;
this DOM-based fallback parses rendered fare cards.
"""

from playwright.sync_api import sync_playwright

from .base_scraper import CI_MODE, BaseScraper

# CI: shorter page load + selector wait; real deployments keep the generous default.
_PAGE_TIMEOUT_MS = 20_000 if CI_MODE else 60_000
_SETTLE_MS = 2_000 if CI_MODE else 5_000


class IndigoScraper(BaseScraper):
    name = "indigo"
    delay_range = (1, 2) if CI_MODE else (8, 15)

    def scrape(self, route: dict, date: str) -> list:
        origin, dest = route["origin"], route["dest"]
        quotes = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=self.random_headers()["User-Agent"])
            url = (
                f"https://www.goindigo.in/flight-booking/select-flight.html"
                f"?Origin={origin}&Destination={dest}&TripType=O&DepartureDate={date}"
            )
            page.goto(url, wait_until="domcontentloaded", timeout=_PAGE_TIMEOUT_MS)
            # Human-like pause: let dynamic results load
            page.wait_for_timeout(_SETTLE_MS + int(self.delay_range[0] * 1000))

            # Selector must be verified against live DOM; keep generic.
            cards = page.query_selector_all("div.flight-item, li.flight-item, [data-testid*='fare']")
            for c in cards:
                text = c.inner_text()
                price = self._extract_price(text)
                if price:
                    quotes.append({
                        "origin": origin,
                        "dest": dest,
                        "carrier": "IndiGo",
                        "fare_class": "economy",
                        "total_fare": price,
                        "currency": "INR",
                        "raw_text": text[:200],
                    })
            browser.close()
        return quotes

    @staticmethod
    def _extract_price(text: str):
        import re

        prices = re.findall(r"₹\s*([\d,]+)", text)
        if not prices:
            return None
        return float(prices[0].replace(",", ""))
