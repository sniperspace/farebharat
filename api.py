"""FastAPI backend — REST API for NSO/RBI consumption.

Run: uvicorn api:app --reload  (port 8000)

Endpoints:
  GET /api/v1/index?frequency=daily&scope=national
  GET /api/v1/routes
  GET /api/v1/quotes?origin=DEL&dest=BOM&limit=100
  GET /api/v1/elasticity?route=DEL-BOM   (lead-time curve)
  GET /health
"""

from collections import defaultdict
from datetime import date

from fastapi import FastAPI, HTTPException, Query

from db import FareQuote, IndexValue, get_session

API_KEY = "apix-demo-key"  # change in production / via env var

app = FastAPI(
    title="FareBharat API — Real-time Airfare Price Index (APIx) for India",
    description="Public API for the FareBharat platform (APIx metric). "
                "For consumption by NSO, RBI and researchers.",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "farebharat", "metric": "APIx"}


@app.get("/api/v1/index")
def get_index(
    frequency: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    scope: str = Query("national"),
    key: str = Query(API_KEY),
    limit: int = 365,
):
    session = get_session()
    rows = (
        session.query(IndexValue)
        .filter_by(frequency=frequency, scope=scope)
        .order_by(IndexValue.index_date.desc())
        .limit(limit)
        .all()
    )
    session.close()
    rows = sorted(rows, key=lambda r: r.index_date)
    return {
        "frequency": frequency,
        "scope": scope,
        "count": len(rows),
        "series": [
            {"date": str(r.index_date), "value": r.value} for r in rows
        ],
    }


@app.get("/api/v1/routes")
def get_routes(key: str = Query(API_KEY)):
    session = get_session()
    pairs = session.query(FareQuote.origin, FareQuote.dest).distinct().all()
    counts = defaultdict(int)
    for o, d in pairs:
        counts[f"{o}-{d}"] += 1
    session.close()
    return {"routes": [{"route": k, "quotes": v} for k, v in sorted(counts.items())]}


@app.get("/api/v1/quotes")
def get_quotes(
    origin: str | None = None,
    dest: str | None = None,
    travel_date: str | None = None,
    limit: int = Query(100, le=1000),
    key: str = Query(API_KEY),
):
    session = get_session()
    q = session.query(FareQuote)
    if origin:
        q = q.filter(FareQuote.origin == origin.upper())
    if dest:
        q = q.filter(FareQuote.dest == dest.upper())
    if travel_date:
        q = q.filter(FareQuote.travel_date == date.fromisoformat(travel_date))
    rows = q.order_by(FareQuote.scraped_date.desc()).limit(limit).all()
    session.close()
    return {
        "count": len(rows),
        "quotes": [
            {
                "origin": r.origin, "dest": r.dest, "carrier": r.carrier,
                "travel_date": str(r.travel_date), "scraped_date": str(r.scraped_date),
                "advance_window": r.advance_window, "fare_class": r.fare_class,
                "base_fare": r.base_fare, "taxes_fees": r.taxes_fees,
                "total_fare": r.total_fare, "source": r.source,
            }
            for r in rows
        ],
    }


@app.get("/api/v1/elasticity")
def get_elasticity(route: str = Query(..., description="e.g. DEL-BOM"), key: str = Query(API_KEY)):
    """Lead-time curve: avg fare vs advance-purchase window."""
    session = get_session()
    origin, dest = route.split("-")
    rows = (
        session.query(FareQuote)
        .filter_by(origin=origin.upper(), dest=dest.upper(), is_outlier=False)
        .all()
    )
    session.close()
    buckets = defaultdict(list)
    for r in rows:
        buckets[r.advance_window].append(r.total_fare)
    curve = sorted(
        ({"window": w, "avg_fare": round(sum(f) / len(f), 0)} for w, f in buckets.items()),
        key=lambda x: x["window"],
    )
    if not curve:
        raise HTTPException(404, "route not found")
    return {"route": route, "lead_time_curve": curve}
