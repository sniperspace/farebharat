"""Compute and store APIx index values from DB quotes.

Usage: python build_index.py
"""

from datetime import date

from db import FareQuote, get_session, IndexValue, init_db
from index_engine import IndexEngine


def upsert_index(session, index_date, frequency, scope, value):
    row = (
        session.query(IndexValue)
        .filter_by(index_date=index_date, frequency=frequency, scope=scope)
        .first()
    )
    if row:
        row.value = value
    else:
        session.add(IndexValue(index_date=index_date, frequency=frequency, scope=scope, value=value))


def main():
    session = get_session()
    eng = IndexEngine()

    quotes = session.query(FareQuote).all()
    if not quotes:
        print("No quotes in DB. Run: python scheduler.py --once")
        return

    base_level = eng.base_price_level(quotes)
    if not base_level:
        print("No usable base-period data.")
        return

    days = sorted({q.scraped_date for q in quotes})
    daily_series = {}

    for day in days:
        result = eng.daily_index(quotes, day, base_level)
        if result["index"] is None:
            continue
        daily_series[str(day)] = result["index"]
        for route, sub in result["routes"].items():
            upsert_index(session, day, "daily", route, sub)
        upsert_index(session, day, "daily", "national", result["index"])

    for wk, val in eng.weekly_index(daily_series).items():
        week_days = [d for d in days if f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}" == wk]
        upsert_index(session, max(week_days), "weekly", "national", val)

    for mo, val in eng.monthly_index(daily_series).items():
        month_days = [d for d in days if f"{d.year}-{d.month:02d}" == mo]
        upsert_index(session, max(month_days), "monthly", "national", val)

    session.commit()
    session.close()
    print(f"Index built: {len(daily_series)} daily values, base=100, base level INR {base_level:.0f}")


if __name__ == "__main__":
    main()
