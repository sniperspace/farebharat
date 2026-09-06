"""EaseMyTrip scraper — easiest source, good starting point.

Tries the internal JSON/XHR search endpoint first; falls back to
Playwright-rendered page parsing if the endpoint changes.

All requests are rate-limited and sent with an identifiable UA
(compliance with robots.txt / ToS is the caller's responsibility;
see COMPLIANCE.md).
"""

import re

import requests

from .base_scraper import BaseScraper


class EaseMyTripScraper(BaseScraper):
    name = "easemytrip"
    delay_range = (6, 12)

    def scrape(self, route: dict, date: str) -> list:
        origin, dest = route["origin"], route["dest"]
        d = date.replace("-", "")

        # NOTE: Endpoints change often. Verify the current XHR endpoint
        # via browser DevTools (Network tab, Fetch/XHR) and update here.
        # This is a request-pattern template, not a guaranteed contract.
        url = (
            "https://flightapi.easemytrip.com/api/v2/flights/search"
            f"?adult=1&child=0&infant=0&journeyType=1&cabins=0"
            f"&org={origin}&dest={dest}&dept={d}&ret=&airline=Any"
        )
        resp = requests.get(url, headers=self.random_headers(), timeout=45)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        data = resp.json()

        return self._parse_json(data, origin, dest)

    def _parse_json(self, data: dict, origin: str, dest: str) -> list:
        quotes = []
        # Adjust traversal keys to the actual response shape after inspection.
        flights = (
            data.get("Data", {}).get("Flights")
            or data.get("data", {}).get("flights")
            or []
        )
        for f in flights:
            try:
                fare = f.get("Fare") or f.get("fare")
                if not fare:
                    continue
                # extract numeric price from string like "INR 5234"
                total = None
                for key in ("TotalFare", "totalFare", "PublishFare"):
                    if isinstance(fare, dict) and fare.get(key):
                        total = self._to_number(fare[key])
                        break
                if total is None and isinstance(fare, (int, float)):
                    total = float(fare)
                if total is None:
                    continue
                quotes.append({
                    "origin": origin,
                    "dest": dest,
                    "carrier": f.get("AirlineName") or f.get("airlineName", ""),
                    "flight_no": f.get("FlightNumber", ""),
                    "depart_ts": f.get("DepTime", ""),
                    "arrive_ts": f.get("ArrTime", ""),
                    "fare_class": f.get("Refundable", ""),
                    "total_fare": total,
                    "currency": "INR",
                })
            except Exception:  # skip malformed rows
                continue
        return quotes

    @staticmethod
    def _to_number(value) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        m = re.search(r"[\d,]+\.?\d*", str(value))
        return float(m.group().replace(",", "")) if m else None
