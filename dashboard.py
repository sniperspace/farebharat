"""FareBharat — APIx Live Dashboard (Streamlit Cloud ready).

Run locally: streamlit run dashboard.py
Deploy:      push to GitHub, connect repo at share.streamlit.io
             (main file: apix/dashboard.py)

Reads directly from data/apix.db which is refreshed every 6 hours by the
GitHub Actions cron workflow (.github/workflows/scrape.yml).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# make local modules importable when Streamlit Cloud sets a different CWD
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
os.chdir(HERE)

from db import FareQuote, IndexValue, get_session  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))

NAVY = "#1a3c6e"
RED = "#c62828"
TEAL = "#00695c"

st.set_page_config(
    page_title="FareBharat — Airfare Price Index India",
    layout="wide",
    page_icon="✈️",
    initial_sidebar_state="expanded",
)

# ---- restrained global styling: typography + metric cards ----
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
      html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
      h1 { font-weight: 700; letter-spacing: -0.5px; }
      [data-testid="stMetric"] {
          background: #f7f9fc;
          border: 1px solid #e3e8f0;
          border-radius: 10px;
          padding: 14px 18px;
      }
      [data-testid="stMetricValue"] { font-weight: 700; }
      [data-testid="stHeader"] { background: none; }
      .block-container { padding-top: 2.2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---- auto-refresh every 10 minutes so newly-pushed data appears ----
st.markdown(
    "<meta http-equiv='refresh' content='600'>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- header
st.title("FareBharat ✈️ Real-time Airfare Price Index for India")
st.caption(
    "APIx · Base = 100 · Jevons index · DGCA passenger-traffic weighted basket · "
    "CPI-aligned methodology · Real fares scraped from live search every 6 hours"
)


@st.cache_data(ttl=300)
def load_index_series(frequency: str, scope: str) -> pd.DataFrame:
    s = get_session()
    rows = (
        s.query(IndexValue)
        .filter_by(frequency=frequency, scope=scope)
        .order_by(IndexValue.index_date)
        .all()
    )
    s.close()
    return pd.DataFrame([{"date": r.index_date, "value": r.value} for r in rows])


@st.cache_data(ttl=300)
def load_route_indices_latest() -> pd.DataFrame:
    s = get_session()
    rows = (
        s.query(IndexValue)
        .filter_by(frequency="daily")
        .filter(IndexValue.scope != "national")
        .order_by(IndexValue.index_date.desc())
        .all()
    )
    s.close()
    if not rows:
        return pd.DataFrame()
    latest = rows[0].index_date
    return pd.DataFrame(
        [{"route": r.scope, "value": r.value} for r in rows if r.index_date == latest]
    )


@st.cache_data(ttl=300)
def load_quotes_df() -> pd.DataFrame:
    s = get_session()
    rows = s.query(FareQuote).filter_by(is_outlier=False).all()
    s.close()
    return pd.DataFrame([
        {
            "origin": r.origin, "dest": r.dest,
            "route": f"{r.origin}-{r.dest}",
            "carrier": r.carrier,
            "advance_window": r.advance_window,
            "travel_date": r.travel_date,
            "scraped_date": r.scraped_date,
            "total_fare": r.total_fare,
            "base_fare": r.base_fare,
            "taxes_fees": r.taxes_fees,
            "source": r.source,
        }
        for r in rows
    ])


@st.cache_data(ttl=300)
def db_stats() -> dict:
    s = get_session()
    q_count = s.query(FareQuote).count()
    real_count = s.query(FareQuote).filter(FareQuote.source != "demo").count()
    sources = [r[0] for r in s.query(FareQuote.source).distinct().all()]
    latest_scrape = (
        s.query(FareQuote).order_by(FareQuote.scraped_date.desc()).first()
    )
    latest_index = (
        s.query(IndexValue)
        .filter_by(frequency="daily", scope="national")
        .order_by(IndexValue.index_date.desc())
        .first()
    )
    s.close()
    return {
        "quotes": q_count,
        "real_quotes": real_count,
        "sources": ", ".join(sorted(set(sources))),
        "latest_scrape": latest_scrape.scraped_date if latest_scrape else None,
        "latest_index": latest_index.value if latest_index else None,
        "latest_index_date": latest_index.index_date if latest_index else None,
    }


# ------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Live Status")
    stats = db_stats()
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    st.write(f"**Now:** {now_ist}")
    st.markdown(
        f"""
        | | |
        |---|---|
        | **Quotes** | {stats['quotes']:,} |
        | **Sources** | {stats['sources'] or '—'} |
        | **Last scrape** | {stats['latest_scrape'] or '—'} |
        | **Index date** | {stats['latest_index_date'] or '—'} |
        """
    )
    st.success("Live scraped data", icon="🟢")

    st.divider()
    st.markdown(
        "**Data pipeline**\n\n"
        "1. GitHub Actions cron (every 6 h)\n"
        "2. Scraper → raw JSON audit trail\n"
        "3. Cleaner → validated DB rows\n"
        "4. Index engine → APIx (Jevons)\n"
        "5. Dashboard auto-refreshes every 10 min"
    )
    st.divider()
    if st.button("Force refresh cache", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ------------------------------------------------------------ KPI row
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
latest_val = stats["latest_index"]
kpi1.metric(
    "Latest APIx (base 100)",
    f"{latest_val:.2f}" if latest_val else "—",
    f"{latest_val - 100:+.2f} vs base" if latest_val else None,
    border=True,
)
kpi2.metric("Quotes collected", f"{stats['real_quotes']:,}", "live scraped", border=True)
kpi3.metric(
    "Last scrape",
    str(stats["latest_scrape"]) if stats["latest_scrape"] else "—",
    "every 6 hours",
    border=True,
)
kpi4.metric("Data source", stats["sources"] or "—", "robots.txt compliant", border=True)

st.divider()

# ------------------------------------------------------------ tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 Index Trend",
    "🗺️ Sector Heatmap",
    "⏱️ Lead-Time Elasticity",
    "🛫 Carrier Comparison",
    "🗂️ Raw Data",
])


def _clean_layout(fig: go.Figure, height: int = 430) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        hovermode="x unified",
        margin=dict(l=30, r=30, t=30, b=30),
        font=dict(family="Inter, sans-serif", size=13),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#eef1f5")
    fig.update_yaxes(showgrid=True, gridcolor="#eef1f5")
    return fig


# ---- Tab 1: national trend --------------------------------------
with tab1:
    st.subheader("National Daily APIx (base = 100)")
    df = load_index_series("daily", "national")
    if df.empty:
        st.info("No data yet. Run: `python scheduler.py --once && python build_index.py`")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["value"], mode="lines+markers",
            name="APIx", line=dict(color=NAVY, width=3),
            fill="tozeroy", fillcolor="rgba(26,60,110,0.06)",
        ))
        fig.add_hline(y=100, line_dash="dash", line_color="grey",
                      annotation_text="Base = 100")
        _clean_layout(fig)
        fig.update_layout(yaxis_title="Index", xaxis_title="Date")
        st.plotly_chart(fig, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Weekly average")
            w = load_index_series("weekly", "national")
            if not w.empty:
                fig_w = px.line(w, x="date", y="value", markers=True)
                fig_w.update_traces(line_color=NAVY)
                _clean_layout(fig_w, height=330)
                fig_w.update_layout(xaxis_title="", yaxis_title="Index")
                st.plotly_chart(fig_w, use_container_width=True)
        with col_b:
            st.subheader("Monthly average")
            m = load_index_series("monthly", "national")
            if not m.empty:
                fig_m = px.bar(m, x="date", y="value", color="value",
                               color_continuous_scale="Blues")
                _clean_layout(fig_m, height=330)
                fig_m.update_layout(xaxis_title="", yaxis_title="Index")
                st.plotly_chart(fig_m, use_container_width=True)

# ---- Tab 2: route heatmap ---------------------------------------
with tab2:
    st.subheader("Sector-wise Fare Heatmap (avg total fare, ₹)")
    quotes_df = load_quotes_df()
    if quotes_df.empty:
        st.info("No quote data yet.")
    else:
        pivot = (
            quotes_df.pivot_table(
                index="route", columns="advance_window",
                values="total_fare", aggfunc="mean",
            )
            .round(0)
        )
        fig = px.imshow(
            pivot,
            color_continuous_scale="RdYlGn_r",
            aspect="auto",
            labels=dict(x="Advance-purchase window (T+n days)", y="Route",
                        color="Avg fare (₹)"),
            text_auto="₹,.0f",
        )
        _clean_layout(fig)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Greener = cheaper sector-window combinations; redder = pricier. "
                   "Built from cleaned, outlier-filtered quotes.")

        st.subheader("Route Sub-Indices (latest day)")
        routes = load_route_indices_latest()
        if not routes.empty:
            routes = routes.sort_values("value", ascending=False)
            fig2 = px.bar(
                routes, x="route", y="value", color="value",
                color_continuous_scale="RdYlGn_r",
                labels={"value": "Index (base=100)", "route": "Route"},
            )
            fig2.add_hline(y=100, line_dash="dash", line_color="grey")
            _clean_layout(fig2)
            st.plotly_chart(fig2, use_container_width=True)

# ---- Tab 3: elasticity ------------------------------------------
with tab3:
    st.subheader("Lead-Time Elasticity — fare vs booking window")
    quotes_df = load_quotes_df()
    if quotes_df.empty:
        st.info("No quote data yet.")
    else:
        route = st.selectbox("Route", sorted(quotes_df["route"].unique()))
        sub = quotes_df[quotes_df["route"] == route]
        curve = (
            sub.groupby("advance_window")["total_fare"]
            .mean().reset_index()
            .sort_values("advance_window")
        )
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=curve["advance_window"], y=curve["total_fare"],
            mode="lines+markers",
            line=dict(color=RED, width=3),
            marker=dict(size=9),
        ))
        _clean_layout(fig)
        fig.update_layout(
            xaxis_title="Days in advance (T+n)",
            yaxis_title="Avg total fare (₹)",
        )
        fig.update_yaxes(tickprefix="₹", tickformat=",")
        st.plotly_chart(fig, use_container_width=True)

        pct = (curve["total_fare"].iloc[0] / curve["total_fare"].iloc[-1] - 1) * 100
        st.info(
            f"Booking at T+{int(curve['advance_window'].iloc[0])} costs "
            f"**{pct:+.0f}%** vs T+{int(curve['advance_window'].iloc[-1])} on {route}."
        )

# ---- Tab 4: carrier comparison ----------------------------------
with tab4:
    st.subheader("Average Total Fare by Carrier")
    quotes_df = load_quotes_df()
    if quotes_df.empty:
        st.info("No quote data yet.")
    else:
        avg = (
            quotes_df.groupby("carrier")["total_fare"]
            .agg(["mean", "count"]).round(0).reset_index()
            .rename(columns={"mean": "avg_fare", "count": "n_quotes"})
            .sort_values("avg_fare")
        )
        fig = px.bar(
            avg, x="carrier", y="avg_fare", color="avg_fare",
            color_continuous_scale="Blues", text="avg_fare",
        )
        fig.update_traces(texttemplate="₹%,.0f", textposition="outside")
        _clean_layout(fig)
        fig.update_layout(yaxis_title="Avg fare (₹)", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            avg, use_container_width=True, hide_index=True,
            column_config={
                "avg_fare": st.column_config.NumberColumn("Avg fare (₹)", format="₹%,.0f"),
                "n_quotes": st.column_config.NumberColumn("Quotes"),
            },
        )

# ---- Tab 5: raw data --------------------------------------------
with tab5:
    st.subheader("Raw Fare Quotes (audit trail)")
    quotes_df = load_quotes_df()
    if quotes_df.empty:
        st.info("No quote data yet.")
    else:
        st.write(f"Showing latest 500 of {len(quotes_df):,} quotes.")
        st.dataframe(
            quotes_df.sort_values("scraped_date", ascending=False).head(500),
            use_container_width=True, hide_index=True,
            column_config={
                "total_fare": st.column_config.NumberColumn("Total (₹)", format="₹%,.0f"),
                "base_fare": st.column_config.NumberColumn("Base (₹)", format="₹%,.0f"),
                "taxes_fees": st.column_config.NumberColumn("Taxes (₹)", format="₹%,.0f"),
                "advance_window": st.column_config.NumberColumn("T+n"),
            },
        )
        st.download_button(
            "Download full dataset (CSV)",
            quotes_df.to_csv(index=False).encode("utf-8"),
            file_name="farebharat_quotes.csv",
            mime="text/csv",
        )

st.divider()
c1, c2 = st.columns([3, 1])
with c1:
    st.caption(
        "FareBharat · Prototype for SIH 2026 · Problem Statement 26056 · MoSPI DIID · "
        "Open source (MIT). Live data pipeline; scraper honours robots.txt "
        "and rate-limits per source ToS."
    )
with c2:
    st.caption(f"Pipeline: GitHub Actions · 6-hourly · source: {stats['sources'] or '—'}")
