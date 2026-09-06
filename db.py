"""Database layer — SQLite by default (zero config), PostgreSQL optional.

Set DATABASE_URL env var to use PostgreSQL:
    DATABASE_URL=postgresql+psycopg2://user:pass@localhost/apix
"""

import os
from datetime import date, datetime

from sqlalchemy import (Float, Integer, String, create_engine,
                        UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///data/apix.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class FareQuote(Base):
    __tablename__ = "fact_fare_quote"
    __table_args__ = (UniqueConstraint("source", "origin", "dest", "travel_date", "carrier", "fare_class", name="uq_quote"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(40))
    origin: Mapped[str] = mapped_column(String(3), index=True)
    dest: Mapped[str] = mapped_column(String(3), index=True)
    travel_date: Mapped[date] = mapped_column(index=True)          # T+n travel date
    scraped_date: Mapped[date] = mapped_column(index=True)         # when observed
    advance_window: Mapped[int] = mapped_column(Integer)           # n in T+n
    carrier: Mapped[str] = mapped_column(String(50))
    flight_no: Mapped[str] = mapped_column(String(15), default="")
    fare_class: Mapped[str] = mapped_column(String(20), default="economy")
    base_fare: Mapped[float] = mapped_column(Float)
    taxes_fees: Mapped[float] = mapped_column(Float, default=0.0)
    total_fare: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    is_outlier: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class IndexValue(Base):
    __tablename__ = "fact_index"
    __table_args__ = (UniqueConstraint("index_date", "frequency", "scope", name="uq_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    index_date: Mapped[date] = mapped_column(index=True)
    frequency: Mapped[str] = mapped_column(String(10))   # daily / weekly / monthly
    scope: Mapped[str] = mapped_column(String(20))       # 'national' or 'DEL-BOM'
    value: Mapped[float] = mapped_column(Float)          # base = 100


def init_db():
    from pathlib import Path

    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(engine)


def get_session():
    init_db()
    return SessionLocal()


def upsert_quotes(quotes: list) -> int:
    """Insert cleaned quotes, skip duplicates."""
    session = get_session()
    inserted = 0
    try:
        for q in quotes:
            exists = (
                session.query(FareQuote)
                .filter_by(
                    source=q["source"], origin=q["origin"], dest=q["dest"],
                    travel_date=q["travel_date"], carrier=q["carrier"],
                    fare_class=q.get("fare_class", "economy"),
                )
                .first()
            )
            if exists:
                continue
            session.add(FareQuote(**q))
            inserted += 1
        session.commit()
    finally:
        session.close()
    return inserted
