"""One-off migration: delete all demo quotes + index values derived from them,
then rebuild the index from real (ixigo) quotes only."""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from db import FareQuote, IndexValue, get_session, init_db  # noqa: E402

init_db()
s = get_session()
n_demo = s.query(FareQuote).filter(FareQuote.source == "demo").delete()
n_idx = s.query(IndexValue).delete()  # rebuild all — old values mixed demo data
s.commit()
print(f"deleted: {n_demo} demo quotes, {n_idx} index rows")
real = s.query(FareQuote).filter(FareQuote.source != "demo").count()
print(f"kept: {real} real quotes")
s.close()
