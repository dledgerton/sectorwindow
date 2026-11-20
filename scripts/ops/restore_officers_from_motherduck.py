"""Copy officer years that MotherDuck has more of than the local database.

Production has officer history back to 2014 that the local database lacks (local
was loaded from 2019 onward). Scoring uses the local database, so without this
the CEO tenure signal sees a shorter history than production's earlier scores did.
Only years where MotherDuck has MORE rows than local are replaced, so recent years
loaded locally are never overwritten.

Run from the repo root:  python scripts/ops/restore_officers_from_motherduck.py [--dry-run]
Needs MOTHERDUCK_TOKEN in .env.local (never printed). Close other programs using the local database first.
"""
import argparse, os
import duckdb
from dotenv import load_dotenv

load_dotenv(".env.local")
token = os.environ.get("MOTHERDUCK_TOKEN")
if not token:
    raise SystemExit("MOTHERDUCK_TOKEN not found in .env.local")
os.environ["motherduck_token"] = token

ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()

db = os.environ.get("DEJ_DUCKDB_PATH") or "data/dej_intelligence.duckdb"
con = duckdb.connect(db)
con.execute("ATTACH 'md:dej_intelligence' AS md (READ_ONLY)")

def cols(catalog):
    return [r[0] for r in con.execute(
        "select column_name from information_schema.columns "
        "where table_catalog=? and table_name='officers' and table_schema='main' order by ordinal_position",
        [catalog]).fetchall()]

local_cols = cols(con.execute("select current_database()").fetchone()[0])
md_cols = cols("md")
common = [c for c in local_cols if c in md_cols and c != "id"]
missing = [c for c in md_cols if c not in local_cols]
print(f"Copying {len(common)} columns; columns only in MotherDuck (skipped): {missing or 'none'}")

md_n = dict(con.execute("select tax_year, count(*) from md.officers group by 1").fetchall())
lo_n = dict(con.execute("select tax_year, count(*) from officers group by 1").fetchall())
years = sorted(y for y, n in md_n.items() if n > lo_n.get(y, 0))
for y in years:
    print(f"  {y}: local={lo_n.get(y, 0):,} MotherDuck={md_n[y]:,} -> use MotherDuck rows")
if not years:
    print("Nothing to restore.")

cl = ", ".join(common)
if not a.dry_run:
    for y in years:
        con.execute(f"delete from officers where tax_year = {y}")
        con.execute(f"insert into officers ({cl}) select {cl} from md.officers where tax_year = {y}")
        print(f"  {y}: done")
    print("officers now:", con.execute("select count(*) from officers").fetchone()[0])
con.close()
