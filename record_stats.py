#!/usr/bin/env python3
"""
Run watch_simple.py, parse its output, and append a row to daily_stats.csv.
Usage: python3 record_stats.py
"""
import subprocess, re, csv, os, datetime

CSV = os.path.join(os.path.dirname(__file__), "daily_stats.csv")
FIELDS = ["timestamp_utc", "reserve", "deposits", "collects", "position_net",
          "external", "return_direct", "return_indirect", "verdict"]

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

    verdict = "unknown"
    if "EXTERNAL CAPITAL" in output:  verdict = "ANOMALY_EXTERNAL"
    elif "RETURN FLOW"    in output:  verdict = "ANOMALY_RETURN"
    elif "COLLAPSE"       in output:  verdict = "DRAINING"
    elif "Consistent with Ponzi" in output: verdict = "STABLE_PONZI"

    return {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "reserve":       reserve,
        "deposits":      deposits,
        "collects":      collects,
        "position_net":  pos_net.replace(",", ""),
        "external":      external,
        "return_direct": ret_direct,
        "return_indirect": ret_indirect,
        "verdict":       verdict,
    }

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
