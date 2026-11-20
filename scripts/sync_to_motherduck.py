"""Sync the local DuckDB (source of truth) to MotherDuck (what the live app reads).

Run from the repo root:  python scripts/sync_to_motherduck.py [--dry-run]

Order matters: organizations first (filings and officers reference them), then
filings, officers, and transition_scores. Never prints the MotherDuck token.
"""
import argparse, logging, os
import duckdb
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("dej.sync")

load_dotenv(".env.local")
LOCAL_DB = os.environ.get("DEJ_DUCKDB_PATH") or "data/dej_intelligence.duckdb"
token = os.environ.get("MOTHERDUCK_TOKEN")
if not token:
    raise SystemExit("MOTHERDUCK_TOKEN not found in .env.local")

ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true", help="Show what would change, write nothing")
args = ap.parse_args()
DRY = args.dry_run

con = duckdb.connect(f"md:dej_intelligence?motherduck_token={token}")
con.execute(f"ATTACH '{LOCAL_DB}' AS local (READ_ONLY)")
log.info(f"Local source: {LOCAL_DB}{'  (DRY RUN)' if DRY else ''}")


def cols(table):
    rows = con.execute(
        "select column_name from information_schema.columns "
        "where table_name=? and table_schema='main' and table_catalog='dej_intelligence' order by ordinal_position",
        [table],
    ).fetchall()
    seen, out = set(), []
    for (c,) in rows:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


# 1. organizations: add new EINs, refresh the classifier columns on existing ones
org_cols = cols("organizations")
cl = ", ".join(org_cols)
new_orgs = con.execute("select count(*) from local.organizations where ein not in (select ein from organizations)").fetchone()[0]
log.info(f"organizations: {new_orgs:,} new EINs to add")
if new_orgs and not DRY:
    con.execute(f"insert into organizations ({cl}) select {cl} from local.organizations where ein not in (select ein from organizations)")

ntee_cols = [c for c in ("ntee_code_classified", "ntee_category_classified", "ntee_confidence", "ntee_reason", "ntee_classified_at") if c in org_cols]
if ntee_cols:
    cond = " or ".join(f"m.{c} is distinct from l.{c}" for c in ntee_cols)
    stale = con.execute(f"select count(*) from organizations m join local.organizations l using (ein) where {cond}").fetchone()[0]
    log.info(f"organizations: {stale:,} rows with newer NTEE classification")
    if stale and not DRY:
        sets = ", ".join(f"{c} = l.{c}" for c in ntee_cols)
        try:
            con.execute(f"update organizations m set {sets} from local.organizations l where m.ein = l.ein and ({cond})")
        except Exception as e:
            log.warning(f"NTEE update failed ({type(e).__name__}); tell Claude, new orgs were still added: {str(e)[:200]}")


# 2. filings and officers: replace any tax year whose row count differs
def sync_by_year(table):
    c = ", ".join(cols(table))
    md = dict(con.execute(f"select tax_year, count(*) from {table} group by 1").fetchall())
    lo = dict(con.execute(f"select tax_year, count(*) from local.{table} group by 1").fetchall())
    for year in sorted(set(md) | set(lo)):
        if md.get(year, 0) == lo.get(year, 0):
            continue
        if lo.get(year, 0) < md.get(year, 0):
            # Never shrink production: MotherDuck has more rows than local for this year.
            log.warning(f"{table} {year}: MotherDuck={md.get(year, 0):,} local={lo.get(year, 0):,} -> SKIPPED (local has fewer rows; production kept as is)")
            continue
        log.info(f"{table} {year}: MotherDuck={md.get(year, 0):,} local={lo.get(year, 0):,} -> replacing")
        if not DRY:
            con.execute(f"delete from {table} where tax_year = {year}")
            con.execute(f"insert into {table} ({c}) select {c} from local.{table} where tax_year = {year}")


sync_by_year("filings")
sync_by_year("officers")

# 3. scores are rebuilt every time
tc = ", ".join(cols("transition_scores"))
log.info("transition_scores: full replace")
if not DRY:
    con.execute("delete from transition_scores")
    con.execute(f"insert into transition_scores ({tc}) select {tc} from local.transition_scores")

log.info("Final MotherDuck counts:")
for t in ["organizations", "filings", "officers", "transition_scores"]:
    log.info(f"  {t}: {con.execute(f'select count(*) from {t}').fetchone()[0]:,}")
con.close()
log.info("Done.")
