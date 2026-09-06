"""Index engine — APIx construction.

Methodology (mirrors CPI practice):
- Jevons (geometric mean) of price relatives per route x advance window
- fixed-basket weights from DGCA passenger traffic (Lasppeyres-style)
- aggregate: weighted arithmetic mean of route sub-indices -> national index
- base period value = 100
"""

import math
from collections import defaultdict
from datetime import date

import yaml


class IndexEngine:
    def __init__(self, weights_file: str = "config/weights.yaml", base_value: float = 100.0):
        with open(weights_file, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        self.route_weights = cfg["route_weights"]  # e.g. {"DEL-BOM": 14.5, ...}
        self.base_date = date.fromisoformat(cfg["base_date"])
        self.base_value = base_value

    def route_price(self, quotes: list, route: str, day, window: int | None = None) -> float | None:
        """Jevons median-of-geomeans price level for a route on a day.

        Uses geometric mean of quoted total fares (min-fare per carrier first,
        to avoid multi-quote bias within the same carrier).
        Accepts date objects or ISO strings for `day`.
        """
        day = str(day)
        per_carrier = defaultdict(list)
        for q in quotes:
            if q.is_outlier:
                continue
            r = f"{q.origin}-{q.dest}"
            if r != route or str(q.scraped_date) != day:
                continue
            if window is not None and q.advance_window != window:
                continue
            per_carrier[q.carrier].append(q.total_fare)
        if not per_carrier:
            return None
        carrier_geomeans = []
        for fares in per_carrier.values():
            carrier_geomeans.append(math.exp(sum(math.log(f) for f in fares) / len(fares)))
        return math.exp(sum(math.log(g) for g in carrier_geomeans) / len(carrier_geomeans))

    def daily_index(self, quotes: list, day, base_price_level: float | None = None) -> dict:
        """Compute national daily index for `day`.

        base_price_level: average route price level on the base date
        (caller computes once from base-period data).
        Returns {"index": float, "routes": {route: sub_index}}
        """
        route_indices = {}
        weighted_sum, weight_total = 0.0, 0.0
        for route, weight in self.route_weights.items():
            price = self.route_price(quotes, route, day)
            if price is None or base_price_level in (None, 0):
                continue
            sub = price / base_price_level * self.base_value
            route_indices[route] = round(sub, 2)
            weighted_sum += sub * weight
            weight_total += weight
        if weight_total == 0:
            return {"index": None, "routes": {}}
        return {"index": round(weighted_sum / weight_total, 2), "routes": route_indices}

    def base_price_level(self, quotes: list, window: int | None = None) -> float | None:
        """Average route price level over the base period (simple mean across routes)."""
        levels = []
        for route in self.route_weights:
            per_day = defaultdict(list)
            for q in quotes:
                if q.is_outlier or f"{q.origin}-{q.dest}" != route:
                    continue
                if window is not None and q.advance_window != window:
                    continue
                per_day[q.scraped_date].append(q.total_fare)
            if per_day:
                days = []
                for fares in per_day.values():
                    days.append(math.exp(sum(math.log(f) for f in fares) / len(fares)))
                levels.append(sum(days) / len(days))
        if not levels:
            return None
        return sum(levels) / len(levels)

    def weekly_index(self, daily_series: dict) -> dict:
        """daily_series: {date: index_value} -> ISO-week averages."""
        buckets = defaultdict(list)
        for d, v in daily_series.items():
            if v is None:
                continue
            iso = date.fromisoformat(str(d)).isocalendar()
            buckets[f"{iso[0]}-W{iso[1]:02d}"].append(v)
        return {wk: round(sum(vs) / len(vs), 2) for wk, vs in sorted(buckets.items())}

    def monthly_index(self, daily_series: dict) -> dict:
        buckets = defaultdict(list)
        for d, v in daily_series.items():
            if v is None:
                continue
            d = date.fromisoformat(str(d))
            buckets[f"{d.year}-{d.month:02d}"].append(v)
        return {mo: round(sum(vs) / len(vs), 2) for mo, vs in sorted(buckets.items())}
