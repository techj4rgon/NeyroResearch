#!/usr/bin/env python3
"""
Run watch_simple.py, parse its output, and append a row to daily_stats.csv.
Usage: python3 record_stats.py
"""
import subprocess, re, csv, os, datetime

CSV = os.path.join(os.path.dirname(__file__), "daily_stats.csv")
FIELDS = ["timestamp_utc", "reserve", "deposits", "collects", "position_net",
          "external", "return_direct", "return_indirect",
          "deposit_mint_coverage", "collects_vs_baseline",
          "cum_collects", "cum_return", "verdict"]

COLLECTS_BASELINE = 540_000   # historical ~$540k per ~9h window

def parse(output):
    def g(pattern, default="0"):
        m = re.search(pattern, output)
        return m.group(1).replace(",", "") if m else default

    reserve      = g(r"\[RESERVE\] platform position holds ([\d,]+)")
    deposits     = g(r"\[DEPOSIT\] user deposits into funnel: ([\d,]+)")
    collects     = g(r"\[SWEEP\] ([\d,]+) USDT left pool")
    pos_net      = g(r"window flow: mints [\d,]+ in - collects [\d,]+ out = (-?[\d,]+)")
    external     = g(r"EXTERNAL: ([\d,]+)")
    ret_direct   = g(r"direct ([\d,]+) \+")
    ret_indirect = g(r"\+ indirect ([\d,]+)")
    coverage     = g(r"deposit/mint coverage: ([\d]+)%")

    collects_int       = int(collects) if collects and collects != "0" else 0
    collects_vs_base   = str(collects_int - COLLECTS_BASELINE)

    verdict = "unknown"
    if "EXTERNAL CAPITAL" in output:     verdict = "ANOMALY_EXTERNAL"
    elif "RETURN FLOW"    in output:     verdict = "ANOMALY_RETURN"
    elif "COLLAPSE"       in output:     verdict = "DRAINING"
    elif "Consistent with Ponzi" in output: verdict = "STABLE_PONZI"

    return {
        "timestamp_utc":         datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "reserve":               reserve,
        "deposits":              deposits,
        "collects":              collects,
        "position_net":          pos_net.replace(",", ""),
        "external":              external,
        "return_direct":         ret_direct,
        "return_indirect":       ret_indirect,
        "deposit_mint_coverage": coverage,
        "collects_vs_baseline":  collects_vs_base,
        "cum_collects":          "0",   # filled in main() after reading history
        "cum_return":            "0",   # filled in main() after reading history
        "verdict":               verdict,
    }

def migrate_csv():
    """Rewrite CSV with updated column schema if it doesn't match FIELDS."""
    if not os.path.exists(CSV):
        return
    with open(CSV, newline="") as f:
        reader = csv.DictReader(f)
        if (reader.fieldnames or []) == FIELDS:
            return
        rows = list(reader)
    with open(CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            for field in FIELDS:
                row.setdefault(field, "")
            w.writerow(row)

def main():
    result = subprocess.run(
        ["python3", os.path.join(os.path.dirname(__file__), "watch_simple.py")],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise SystemExit(result.returncode)

    row = parse(result.stdout)

    migrate_csv()

    # Accumulate running totals using one row per calendar date (the last run that day)
    # to avoid double-counting from overlapping 9h scan windows.
    cum_collects = 0
    cum_return   = 0
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    if os.path.exists(CSV):
        by_date = {}
        with open(CSV, newline="") as f:
            for r in csv.DictReader(f):
                date = (r.get("timestamp_utc") or "")[:10]
                if date and date != today:
                    by_date[date] = r   # last row wins for each prior date
        for r in by_date.values():
            try: cum_collects += int(r.get("collects") or 0)
            except ValueError: pass
            try: cum_return += int(r.get("return_direct") or 0) + int(r.get("return_indirect") or 0)
            except ValueError: pass
    row["cum_collects"] = str(cum_collects + int(row["collects"] or 0))
    row["cum_return"]   = str(cum_return + int(row["return_direct"] or 0) + int(row["return_indirect"] or 0))

    write_header = not os.path.exists(CSV)
    with open(CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        w.writerow(row)

    print(f"\n[recorded] {CSV}")
    print("  " + ", ".join(f"{k}={v}" for k, v in row.items()))

if __name__ == "__main__":
    main()
