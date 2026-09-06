"""Demo data generator — produces ~35 days of realistic synthetic quotes
so the index, API and dashboard work immediately (plug & play),
before real scraping accumulates data.

Dynamic pricing model: base fare per route x carrier, plus
- advance-window effect (T+1 much costlier)
- day-of-week effect (Fri/Sun premium)
- noise + occasional spikes
"""

import random
from datetime import date, datetime, timedelta

from cleaner import clean_quotes
from db import get_session, upsert_quotes

ROUTE_BASES = {
    "DEL-BOM": 5200, "DEL-BLR": 6100, "BOM-BLR": 4200,
    "DEL-CCU": 5800, "BLR-HYD": 3100, "MAA-DEL": 6300,
}
CARRIERS = [
    ("IndiGo", 1.00), ("Air India", 1.06), ("Akasa Air", 0.97),
    ("SpiceJet", 0.94), ("Air India Express", 0.92),
]


def generate_days(days: int = 35) -> int:
    today = date.today()
    start = today - timedelta(days=days)
    all_clean = []
    for i in range(days):
        obs_day = start + timedelta(days=i)
        for route, base in ROUTE_BASES.items():
            origin, dest = route.split("-")
            for window in [1, 7, 15, 30, 45]:
                travel = obs_day + timedelta(days=window)
                for carrier, mult in CARRIERS:
                    if random.random() < 0.12:  # sold-out / no quote
                        continue
                    # dynamic pricing model
                    window_mult = 1 + 0.55 * math_exp_decay(window)
                    dow = obs_day.weekday()
                    dow_mult = 1.15 if dow in (4, 6) else (1.05 if dow in (0, 5) else 1.0)
                    fare = base * mult * window_mult * dow_mult * random.uniform(0.90, 1.12)
                    if random.random() < 0.03:  # demand spike
                        fare *= random.uniform(1.5, 2.2)
                    all_clean.append({
                        "source": "demo",
                        "origin": origin, "dest": dest,
                        "travel_date": travel.isoformat(),
                        "scraped_date": obs_day.isoformat(),
                        "advance_window": window,
                        "carrier": carrier,
                        "fare_class": "economy",
                        "total_fare": round(fare, 2),
                        "currency": "INR",
                    })
    cleaned = clean_quotes(all_clean)
    n = upsert_quotes(cleaned)
    return n


def math_exp_decay(window: int) -> float:
    return pow(0.95, window)


if __name__ == "__main__":
    from db import init_db

    init_db()
    n = generate_days(35)
    print(f"Inserted {n} demo quotes (35 days back-test data)")
