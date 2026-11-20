"""
One-off migration: widen the filings.source CHECK constraint to allow
'nccs_core_990' and 'nccs_core_990ez' (used by nccs_loader_duckdb.py for the
current NCCS core files, tax year 2022+).

DuckDB can't alter a CHECK constraint in place, so this rebuilds the table:
copy rows (ids included) into a new table with the wider constraint, drop the
old one, rename, and recreate the indexes. Runs in one transaction.

Idempotent: exits without changes if the constraint already allows the values.
Back up data/dej_intelligence.duckdb before running.
"""
import duckdb

from nccs_loader_duckdb import get_db_path

OLD_LIST = "'nccs_pf', 'propublica', 'manual'"
NEW_LIST = "'nccs_pf', 'nccs_core_990', 'nccs_core_990ez', 'propublica', 'manual'"

INDEXES = [
    "create index idx_filings_ein_year     on filings(ein, tax_year)",
    "create index idx_filings_year         on filings(tax_year)",
    "create index idx_filings_source       on filings(source)",
    "create index idx_filings_partial_year on filings(partial_year)",
]


def main() -> None:
    db_path = get_db_path()
    print(f"Database: {db_path}")
    con = duckdb.connect(db_path)

    ddl = con.execute(
        "select sql from duckdb_tables() where table_name = 'filings'"
    ).fetchone()[0]
    if "nccs_core_990ez" in ddl:
        print("filings.source already allows nccs_core_* — nothing to do.")
        return
    if OLD_LIST not in ddl:
        raise SystemExit(f"Unexpected filings DDL, aborting:\n{ddl}")

    new_ddl = ddl.replace(OLD_LIST, NEW_LIST).replace(
        "CREATE TABLE filings(", "CREATE TABLE filings_new(", 1
    )
    cols = [r[0] for r in con.execute(
        "select column_name from information_schema.columns "
        "where table_name = 'filings' order by ordinal_position"
    ).fetchall()]
    col_list = ", ".join(f'"{c}"' for c in cols)
    before = con.execute("select count(*), max(id) from filings").fetchone()

    con.execute("begin transaction")
    try:
        con.execute(new_ddl)
        con.execute(f"insert into filings_new ({col_list}) select {col_list} from filings")
        con.execute("drop table filings")
        con.execute("alter table filings_new rename to filings")
        for stmt in INDEXES:
            con.execute(stmt)
        after = con.execute("select count(*), max(id) from filings").fetchone()
        if after != before:
            raise RuntimeError(f"row count/max id mismatch: before={before} after={after}")
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise

    print(f"✓ rebuilt filings: {after[0]:,} rows, max id {after[1]}")
    con.close()


if __name__ == "__main__":
    main()
