#!/usr/bin/env python3
"""Check whether new source data has been published since the last refresh.

Standard library only, so it runs under launchd without the project venv.

  python3 scripts/ops/check_freshness.py                 # report only
  python3 scripts/ops/check_freshness.py --notify        # also post a macOS notification when something is new
  python3 scripts/ops/check_freshness.py --mark-refreshed  # record current remote state as the baseline

Sources checked: NCCS Core (new layout), IRS TEOS 990 XML annual indexes, IRS BMF files.
State file: data/freshness_state.json
"""
import argparse, datetime as dt, json, subprocess, sys, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "freshness_state.json"
DB = ROOT / "data" / "dej_intelligence.duckdb"

NCCS = "https://nccsdata.s3.us-east-1.amazonaws.com/processed/core/{y}/{f}/core_{y}_{f}.csv"
TEOS = "https://apps.irs.gov/pub/epostcard/990/xml/{y}/index_{y}.csv"
BMF = [f"https://www.irs.gov/pub/irs-soi/eo{i}.csv" for i in (1, 2, 3, 4)]
UA = {"User-Agent": "SectorWindow-freshness-check/1.0"}


def head(url):
    """Return a short fingerprint of a remote file, or None if it does not exist.

    The fingerprint is the Last-Modified time. Some servers (the IRS one) report the file size
    inconsistently between requests, so size is used only when there is no Last-Modified header.
    """
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={**UA, **({"Range": "bytes=0-0"} if method == "GET" else {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                h = r.headers
                if h.get("Last-Modified"):
                    return h["Last-Modified"]
                size = h.get("Content-Range", "").split("/")[-1] or h.get("Content-Length")
                if size:
                    return f"size:{size}"
                if method == "HEAD":
                    continue
                return "exists"
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            if method == "HEAD":
                continue
            return f"error:{e.code}"
        except Exception as e:  # network trouble: do not treat as "new data"
            return f"error:{type(e).__name__}"
    return None


def targets():
    y = dt.date.today().year
    t = {}
    for yr in range(2022, y + 1):
        for f in ("990", "990ez"):
            t[f"NCCS {f.upper()} tax year {yr}"] = NCCS.format(y=yr, f=f)
    for yr in (y - 1, y):
        t[f"IRS 990 XML index {yr}"] = TEOS.format(y=yr)
    for i, u in enumerate(BMF, 1):
        t[f"IRS BMF eo{i}"] = u
    return t


def local_age():
    if not DB.exists():
        return "local database not found"
    d = dt.datetime.fromtimestamp(DB.stat().st_mtime)
    return f"local database last written {d:%Y-%m-%d} ({(dt.datetime.now() - d).days} days ago)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--mark-refreshed", action="store_true")
    a = ap.parse_args()

    now = {name: head(url) for name, url in targets().items()}
    errors = {k: v for k, v in now.items() if v and v.startswith("error:")}
    now = {k: v for k, v in now.items() if k not in errors}
    old = json.loads(STATE.read_text())["sources"] if STATE.exists() else None

    if a.mark_refreshed or old is None:
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps({"checked": dt.datetime.now().isoformat(timespec="seconds"), "sources": now}, indent=2))
        print("Baseline recorded." if old is None and not a.mark_refreshed else "Baseline updated after refresh.")
        print(local_age())
        return 0

    new, changed = [], []
    for k, v in now.items():
        if v is None:
            continue
        if old.get(k) is None:
            new.append(k)
        elif old[k] != v:
            changed.append(k)

    lines = [local_age()]
    if new:
        lines.append("NEW since last refresh: " + "; ".join(new))
    if changed:
        lines.append("UPDATED since last refresh: " + "; ".join(changed))
    if not new and not changed:
        lines.append("Nothing new published since the last refresh.")
    if errors:
        lines.append(f"Could not check {len(errors)} source(s) (network or site trouble); will retry next run.")
    print("\n".join(lines))

    if a.notify and (new or changed) and sys.platform == "darwin":
        msg = f"{len(new)} new and {len(changed)} updated data source(s). Run scripts/ops/refresh.sh"
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "SectorWindow data"'], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
