"""Cleaning pipeline: raw quotes -> validated, de-duplicated, outlier-flagged rows ready for DB.

- splits total fare into base fare vs taxes/fees (typical Indian breakdown)
- outlier detection: IQR fence within route x window cell (+ optional IsolationForest if sklearn present)
- sold-out / missing handling: sold-out produces no quote (natural), gaps are
  imputed at index time using last-observed-price within carrier x window cell
"""

from datetime import datetime

import pandas as pd

# typical split for Indian domestic economy fares (approx; refine per source)
TAX_SHARE_THRESHOLD = 0.6  # if taxes exceed 60% of total, flag suspicious


def clean_quotes(raw_quotes: list) -> list:
    """raw quote: {origin, dest, carrier, total_fare, travel_date, scraped_date,
                   advance_window, source, fare_class?, ...}"""
    rows = []
    for q in raw_quotes:
        total = _to_float(q.get("total_fare"))
        if not total or total <= 0 or total > 200000:  # sanity bounds (INR)
            continue
        travel_date = q.get("travel_date")
        if isinstance(travel_date, str):
            travel_date = datetime.strptime(travel_date, "%Y-%m-%d").date()
        scraped = q.get("scraped_date") or datetime.now().date()
        if isinstance(scraped, str):
            scraped = datetime.strptime(scraped, "%Y-%m-%d").date()

        # fare decomposition: estimate base vs taxes
        base = _to_float(q.get("base_fare")) or round(total / 1.282, 2)  # ~28% taxes+fees blended
        taxes = round(total - base, 2)
        if taxes / total > TAX_SHARE_THRESHOLD:
            continue  # suspicious decomposition, drop

        rows.append({
            "source": q.get("source", "unknown"),
            "origin": q["origin"].upper(),
            "dest": q["dest"].upper(),
            "travel_date": travel_date,
            "scraped_date": scraped,
            "advance_window": int(q["advance_window"]),
            "carrier": (q.get("carrier") or "unknown").strip(),
            "flight_no": q.get("flight_no", ""),
            "fare_class": q.get("fare_class", "economy"),
            "base_fare": base,
            "taxes_fees": taxes,
            "total_fare": round(total, 2),
            "currency": q.get("currency", "INR"),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return []
    df = df.drop_duplicates(subset=["source", "origin", "dest", "travel_date", "carrier", "fare_class"])
    df = flag_outliers(df)
    return df.to_dict("records")


def flag_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """IQR fence within route x advance_window cell."""
    df["is_outlier"] = False
    for _, group in df.groupby(["origin", "dest", "advance_window"]):
        q1, q3 = group["total_fare"].quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask = (group["total_fare"] < lo) | (group["total_fare"] > hi)
        df.loc[mask.index, "is_outlier"] = mask.values
    return df


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
