#!/usr/bin/env python3
"""Compensation by NTEE sector and revenue band, from Form 990 Part VII.

Writes aggregate CSVs to reports/comp/ (no names, aggregates only).
Usage: python scripts/reports/comp_by_sector_and_size.py [--year 2023] [--db data/dej_intelligence.duckdb]

Definitions
  Highest-paid person: the largest pay (default: comp_reportable_org, pay from the filing organization only; --pay total uses comp_total) among current (not former) people listed on Part VII
                       for the organization-year, counting only organizations where that amount is > 0.
  CEO/ED: the largest comp_total among current people whose title looks like a chief executive
          (CEO, chief executive, executive director, head of school), excluding deputy/assistant/
          associate/vice/past/elect/co-titles. Paid (> 0) only.
  Sector: first letter of the IRS NTEE code, else of the classifier's code, grouped into the ten NTEE broad groups.
  Revenue: total revenue on the organization's Form 990 for the same tax year.
"""
import argparse
from pathlib import Path
import duckdb

ap = argparse.ArgumentParser()
ap.add_argument("--year", type=int, default=2023)
ap.add_argument("--db", default="data/dej_intelligence.duckdb")
ap.add_argument("--out", default="reports/comp")
ap.add_argument("--pay", choices=["org","total"], default="org", help="org = pay from the filing organization only (default); total = adds related-org pay and benefits")
ap.add_argument("--states", default="", help="comma list, e.g. DC,MD,VA (default: all loaded states)")
a = ap.parse_args()
PAYCOL = "comp_reportable_org" if a.pay == "org" else "comp_total"
STATES = [x.strip().upper() for x in a.states.split(",") if x.strip()]
STATE_SQL = ("where state in (" + ",".join(repr(x) for x in STATES) + ")") if STATES else ""
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
c = duckdb.connect(a.db, read_only=True)

c.execute(f"""
create or replace temp table base as
with pay as (
  select ein,
         max({PAYCOL}) filter (where not coalesce(is_former,false) and {PAYCOL} > 0) as top_pay,
         max({PAYCOL}) filter (where not coalesce(is_former,false) and {PAYCOL} > 0
           and regexp_matches(upper(coalesce(title_normalized, title_raw, '')),
               '(CEO|CHIEF EXEC|EXEC(UTIVE)? ?DIR|HEAD OF SCHOOL)')
           and not regexp_matches(upper(coalesce(title_normalized, title_raw, '')),
               '(DEPUTY|ASSIST|ASSOC|VICE|VP|PAST|FORMER|ELECT|CO-?CEO|CO-?EXEC|INTERIM)')) as ceo_pay,
         count(*) filter (where not coalesce(is_former,false)) as people
  from officers where tax_year = {a.year} group by 1),
rev as (
  select ein, max(total_revenue) as revenue
  from filings where tax_year = {a.year} and source = 'nccs_core_990' group by 1),
org as (
  select ein, upper(substr(coalesce(ntee_code, ntee_code_classified), 1, 1)) as letter from organizations {STATE_SQL})
select p.ein, o.letter, r.revenue, p.top_pay, p.ceo_pay
from pay p join rev r using (ein) {'join' if STATES else 'left join'} org o using (ein)
where r.revenue is not null
""")

c.execute("""
create or replace temp table lab as
select *,
  case when letter = 'A' then '1 Arts, Culture & Humanities'
       when letter = 'B' then '2 Education'
       when letter in ('C','D') then '3 Environment & Animals'
       when letter in ('E','F','G','H') then '4 Health'
       when letter in ('I','J','K','L','M','N','O','P') then '5 Human Services'
       when letter = 'Q' then '6 International'
       when letter in ('R','S','T','U','V','W') then '7 Public & Societal Benefit'
       when letter = 'X' then '8 Religion-Related'
       when letter = 'Y' then '9 Mutual & Membership Benefit'
       else '10 Unclassified' end as sector,
  case when revenue < 500000 then '1 Under $500K'
       when revenue < 1000000 then '2 $500K-$1M'
       when revenue < 2500000 then '3 $1M-$2.5M'
       when revenue < 5000000 then '4 $2.5M-$5M'
       when revenue < 10000000 then '5 $5M-$10M'
       when revenue < 25000000 then '6 $10M-$25M'
       when revenue < 50000000 then '7 $25M-$50M'
       when revenue < 100000000 then '8 $50M-$100M'
       else '9 $100M+' end as band
from base
""")

def stats(group_cols, col, name):
    g = ", ".join(group_cols)
    sel = (g + ",") if group_cols else ""
    tail = f"group by {g} order by {g}" if group_cols else ""
    return f"""
      select {sel}
        count(*) as orgs_with_filing,
        count({col}) as paid_n,
        round(100.0*count({col})/count(*),1) as pct_paid,
        round(quantile_cont({col}, 0.25)) as p25,
        round(quantile_cont({col}, 0.50)) as median,
        round(quantile_cont({col}, 0.75)) as p75,
        round(quantile_cont({col}, 0.90)) as p90,
        round(avg({col})) as mean
      from lab {tail}"""

def dump(sql, fname):
    cur = c.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    with open(out / fname, "w") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join("" if v is None else str(v).replace(",", ";") for v in r) + "\n")
    print(fname, len(rows), "rows")

for col, tag in (("top_pay", "top"), ("ceo_pay", "ceo")):
    dump(stats([], col, tag), f"{tag}_overall_{a.year}.csv")
    dump(stats(["sector"], col, tag), f"{tag}_by_sector_{a.year}.csv")
    dump(stats(["band"], col, tag), f"{tag}_by_band_{a.year}.csv")
    dump(stats(["sector", "band"], col, tag), f"{tag}_sector_band_{a.year}.csv")
    dump(stats(["letter"], col, tag), f"{tag}_by_letter_{a.year}.csv")
