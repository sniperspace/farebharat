"""Ixigo scraper — REAL implementation using their internal search-stream API.

Endpoint (discovered via probe, see probe/discover.py):
    GET https://www.ixigo.com/flights/v2/search/stream
        ?origin=DEL&destination=BOM&leave=130926&return=
        &adults=1&children=0&infants=0&class=E
        &airlineFareType=REGULAR&version=2.0&searchSrc=Search%20Form

Auth is via static headers (apikey/clientid/deviceid) — no dynamic token.
Response is an SSE stream (text/event-stream) whose single SPLIT event
carries flightFare[] with displayFare per flight + seat availability.

Public, non-login data; low request volume; see COMPLIANCE notes in README.
"""

import json
from datetime import datetime

import requests

from .base_scraper import BaseScraper

_STREAM_URL = "https://www.ixigo.com/flights/v2/search/stream"

# airline code -> display name (flight number prefix)
_AIRLINES = {
    "AI": "Air India",
    "6E": "IndiGo",
    "QP": "Akasa Air",
    "SG": "SpiceJet",
    "IX": "Air India Express",
    "UK": "Vistara",
    "G8": "Go First",
    "I5": "AirAsia India",
    "SJ": "SpiceJet",  # spare
}

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "content-type": "application/json; charset=UTF-8",
    "apikey": "ixiweb!2$",
    "clientid": "ixiweb",
    "ixisrc": "ixiweb",
    "appversion": "2",
    "deviceid": "0ad4d02f15784a539f76",
    "uuid": "0ad4d02f15784a539f76",
    "x-request-webappversion": "2.80.0",
    "Accept-Language": "en-IN",
    "Origin": "https://www.ixigo.com",
}


def _airline_from_flight_key(flight_key: str) -> str:
    # "DEL-BOM-AI2951-13092026" -> 2-char IATA code ("AI", "6E", ...) -> name
    try:
        num = flight_key.split("-")[2]
        return _AIRLINES.get(num[:2].upper(), f"IX-{num[:2].upper()}")
    except Exception:  # noqa: BLE001
        return ""


class IxigoScraper(BaseScraper):
    name = "ixigo"
    delay_range = (6, 12)

    def scrape(self, route: dict, date: str) -> list:
        origin, dest = route["origin"], route["dest"]
        if hasattr(date, "strftime"):
            leave = date.strftime("%d%m%y")
        else:
            y, m, d = map(int, str(date).split("-"))
            leave = datetime(y, m, d).strftime("%d%m%y")

        params = (
            f"?origin={origin}&destination={dest}&leave={leave}&return="
            "&adults=1&children=0&infants=0&class=E"
            "&airlineFareType=REGULAR&version=2.0&searchSrc=Search%20Form"
        )
        headers = dict(_HEADERS)
        headers["Referer"] = (
            f"https://www.ixigo.com/search/result/flight/{origin}/{dest}/{leave}/1/0/0/E"
        )

        resp = requests.get(
            _STREAM_URL + params, headers=headers, timeout=90, stream=True
        )
        from .base_scraper import logging

        logging.info(
            "ixigo %s-%s %s HTTP %d, %d bytes, ctype=%s",
            origin, dest, leave, resp.status_code, len(resp.content),
            resp.headers.get("content-type", ""),
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:120]}")

        quotes = []
        for part in resp.content.decode("utf-8", errors="replace").split("data:"):
            part = part.strip()
            if not part:
                continue
            try:
                event = json.loads(part)
            except Exception:  # incomplete chunk
                continue
            data = event.get("data") or {}
            for journey in data.get("flightJourneys") or []:
                for ff in journey.get("flightFare") or []:
                    fkey = ff.get("flightKeys") or ""
                    carrier = _airline_from_flight_key(fkey)
                    try:
                        flight_no = fkey.split("-")[2]  # e.g. AI2951
                    except IndexError:
                        flight_no = fkey[:15]
                    for fare in ff.get("fares") or []:
                        total = (fare.get("fareDetails") or {}).get("displayFare")
                        if not total:
                            continue
                        meta = (fare.get("fareMetadata") or [{}])[0]
                        quotes.append({
                            "origin": origin,
                            "dest": dest,
                            "carrier": carrier,
                            "flight_no": flight_no,
                            "travel_date": date.isoformat() if hasattr(date, "isoformat") else str(date),
                            "fare_class": (meta.get("cabinClass") or "ECONOMY").title(),
                            "total_fare": float(total),
                            "base_fare": None,
                            "taxes_fees": None,
                            "currency": "INR",
                            "seat_remaining": meta.get("seatRemaining"),
                            "refundable": ff.get("refundableType", ""),
                            "source": "ixigo",
                        })
        return quotes
