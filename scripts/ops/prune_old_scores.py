"""Keep only the newest transition_scores row per org.

compute_signals.py adds a new row per org per scoring date and never removes old ones,
and the app's queries join transition_scores on ein without picking the latest row.
Without this step an org scored on two different dates appears twice in the app.
Old scores are not lost: refresh.sh backs up the database first.

Run from the repo root:  python scripts/ops/prune_old_scores.py [--dry-run]
"""
import argparse, os
import duckdb
from dotenv import load_dotenv

load_dotenv(".env.local")
db = os.environ.get("DEJ_DUCKDB_PATH") or "data/dej_intelligence.duckdb"
ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()

con = duckdb.connect(db)
total, orgs = con.execute("select count(*), count(distinct ein) from transition_scores").fetchone()
stale = con.execute(
    "select count(*) from transition_scores t "
    "where scored_at < (select max(scored_at) from transition_scores x where x.ein = t.ein)"
).fetchone()[0]
print(f"transition_scores: {total:,} rows for {orgs:,} orgs; {stale:,} older rows to remove")
if stale and not a.dry_run:
    con.execute(
        "delete from transition_scores where scored_at < "
        "(select max(scored_at) from (select ein e, scored_at from transition_scores) x where x.e = transition_scores.ein)"
    )
    total, orgs = con.execute("select count(*), count(distinct ein) from transition_scores").fetchone()
    print(f"after: {total:,} rows for {orgs:,} orgs")
con.close()
