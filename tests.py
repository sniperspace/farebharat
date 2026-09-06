"""Tests — run with:  pytest -q"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("DATABASE_URL", "sqlite:///data/test.db")

from cleaner import clean_quotes, flag_outliers  # noqa: E402
from index_engine import IndexEngine  # noqa: E402


def _quote(total, **kw):
    base = {
        "source": "test", "origin": "DEL", "dest": "BOM",
        "travel_date": "2026-10-01", "scraped_date": "2026-09-01",
        "advance_window": 7, "carrier": "IndiGo", "total_fare": total,
    }
    base.update(kw)
    return base


def test_clean_bounds():
    rows = clean_quotes([_quote(5000), _quote(-10), _quote(999999)])
    assert len(rows) == 1 and rows[0]["total_fare"] == 5000


def test_clean_decomposition():
    rows = clean_quotes([_quote(5000)])
    assert abs(rows[0]["base_fare"] + rows[0]["taxes_fees"] - 5000) < 0.01


def test_dedup():
    rows = clean_quotes([_quote(5000), _quote(5000)])
    assert len(rows) == 1


def test_outlier_flagged():
    carriers = ["IndiGo", "Air India", "Akasa", "SpiceJet", "AIX", "Vistara"]
    data = [_quote(t, carrier=c) for t, c in zip([5000, 5200, 5100, 5300, 4900, 50000], carriers)]
    df = flag_outliers(__import__("pandas").DataFrame(clean_quotes(data)))
    assert df["is_outlier"].sum() >= 1


def test_route_price_jevons():
    eng = IndexEngine("config/weights.yaml")

    class Q:
        def __init__(self, o, d, carrier, fare, day="2026-09-01", win=7, outlier=False):
            self.origin, self.dest, self.carrier = o, d, carrier
            self.total_fare, self.scraped_date, self.advance_window = fare, day, win
            self.is_outlier = outlier

    from datetime import date

    quotes = [
        Q("DEL", "BOM", "IndiGo", 5000), Q("DEL", "BOM", "IndiGo", 5100),
        Q("DEL", "BOM", "Air India", 6000), Q("DEL", "BOM", "X", 999999, outlier=True),
    ]
    p = eng.route_price(quotes, "DEL-BOM", date(2026, 9, 1))
    assert 5000 < p < 6000  # geometric mean across carriers, outlier excluded


def test_index_direction():
    eng = IndexEngine("config/weights.yaml")

    class Q:
        def __init__(self, o, d, fare, day):
            self.origin, self.dest, self.carrier = o, d, "T"
            self.total_fare, self.scraped_date, self.advance_window = fare, day, 7
            self.is_outlier = False

    from datetime import date

    base_quotes = [Q("DEL", "BOM", 5000, "2026-09-01")]
    base_level = eng.base_price_level(base_quotes)

    up = [Q("DEL", "BOM", 6000, "2026-09-02")]
    down = [Q("DEL", "BOM", 4000, "2026-09-02")]

    i_up = eng.daily_index(up, date(2026, 9, 2), base_level)["index"]
    i_down = eng.daily_index(down, date(2026, 9, 2), base_level)["index"]
    assert i_up > 100 > i_down
