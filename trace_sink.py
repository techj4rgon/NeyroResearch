#!/usr/bin/env python3
"""
Trace the new unknown sink addresses and classify them.
Targets:
  SINK   0x11df85051f8f7bb3116714990a903cba55975794  (received $10,501 from platform collect)
  FWDTO  0xc7eb9ace7efec296271f1836df524469876c9ec0  (where sink forwarded)
"""
import json, urllib.request, time
RPCS = ["https://bsc-rpc.publicnode.com", "https://bsc.drpc.org"]
USDT  = "0x55d398326f99059ff775485246999027b3197955"
POOL  = "0x92b7807bf19b7dddf89b706143896d05228f3121".lower()
TS    = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
LOOKBACK = 70000; CHUNK = 10000

CLUSTER = {
    "0xe197f1229f7625d74780f1f6be2b9552566fa1e0": "funnel",
    "0x8b45cda448cc26e7f55ef3e77374c7cae8199b61": "bot",
    "0x42c8d37f4f4d0ec6644248d515d7fc849a2a5f61": "collector",
    "0x1a2755eb8f2caee1e69aed75e9de6328fef3488e": "relay",
    "0xc105000dd757d00103e0fb18f0c9ed1a8030fe6b": "hub",
    "0xb16cd608ec3f751f2f316ead1f7601131bbf0400": "distributor",
    "0xa02c3b70339730368a9eb6f168124171baa38365": "passthrough",
}
BINANCE = {
    "0x8894e0a0c962cb723c1976a4421c95949be2d4e3": "Binance 51",
    "0xe2fc31f816a9b94326492132018c3aecc4a93ae1": "Binance",
    "0x515b72ed8a97f42c568d6a143232775018f133c8": "Binance",
    "0x161ba15a5f335c9f06bb5bbb0a9ce14076fbb645": "Binance",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance 8",
    "0x29bdfbf7d27462a2d115748ace2bd71a2646946c": "Binance 16",
    "0x3c783c21a0383057d128bae431894a5c19f9cf06": "Binance",
    "0x835678a611b28684005a5e2233695fb6cbbb0007": "Binance",
}
SWEEP_ROUTE = {
    "0x233c5370ccfb3cd7409d9a3fb98ab94de94cb4cd": "CEX-routing processor",
    "0x5a8e12d1f7148886fe35f6fa04f5a2c2b60ac354": "sweep-hop",
    "0x884c7f4778bb1831a7f2691c194cd51e9644f60e": "Binance deposit",
    "0x88bbcaeeaf0dca4ad50e8aab9387cd78c60be758": "Binance deposit",
}

TARGETS = {
    "0x11df85051f8f7bb3116714990a903cba55975794": "SINK",
    "0xc7eb9ace7efec296271f1836df524469876c9ec0": "FWDTO",
}

def _post(u, m, p, t=24):
    pl = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    try:
        req = urllib.request.Request(u, data=pl, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=t) as r:
            return json.loads(r.read()).get("result")
    except Exception:
        return None

def rpc(m, p, retries=4):
    for _ in range(retries):
        for u in RPCS:
            r = _post(u, m, p)
            if r is not None: return r
        time.sleep(0.4)
    return None

def pad(a): return "0x" + "0" * 24 + a[2:].lower()

def scan_logs(params):
    out = []; lo = params["_lo"]; hi = params["_hi"]; b = lo
    while b <= hi:
        e = min(b + CHUNK - 1, hi)
        q = dict(params); q.pop("_lo"); q.pop("_hi"); q["fromBlock"] = hex(b); q["toBlock"] = hex(e)
        r = rpc("eth_getLogs", [q])
        if isinstance(r, list): out += r
        b = e + 1
    return out

def transfers_from(addr, lo, hi):
    logs = scan_logs({"address": USDT, "topics": [TS, pad(addr), None], "_lo": lo, "_hi": hi})
    return [("0x" + lg["topics"][1][26:].lower(), "0x" + lg["topics"][2][26:].lower(), int(lg["data"], 16) / 1e18) for lg in logs]

def transfers_to(addr, lo, hi):
    logs = scan_logs({"address": USDT, "topics": [TS, None, pad(addr)], "_lo": lo, "_hi": hi})
    return [("0x" + lg["topics"][1][26:].lower(), "0x" + lg["topics"][2][26:].lower(), int(lg["data"], 16) / 1e18) for lg in logs]

def classify(addr):
    a = (addr or "").lower()
    if a in CLUSTER:      return f"CLUSTER:{CLUSTER[a]}"
    if a in BINANCE:      return f"BINANCE:{BINANCE[a]}"
    if a in SWEEP_ROUTE:  return f"SWEEP:{SWEEP_ROUTE[a]}"
    if a == POOL:         return "POOL"
    return "unknown"

def is_contract(addr):
    code = rpc("eth_getCode", [addr, "latest"])
    return isinstance(code, str) and len(code) > 4

def usdt_balance(addr):
    data = "0x70a08231" + "0" * 24 + addr[2:].lower()
    r = rpc("eth_call", [{"to": USDT, "data": data}, "latest"])
    return int(r, 16) / 1e18 if isinstance(r, str) else None

def bnb_balance(addr):
    r = rpc("eth_getBalance", [addr, "latest"])
    return int(r, 16) / 1e18 if isinstance(r, str) else None

def main():
    cur = int(rpc("eth_blockNumber", []), 16)
    lo  = cur - LOOKBACK
    print(f"Block window: {lo} .. {cur}  (~{(cur-lo)*0.45/3600:.1f}h)\n")

    for addr, label in TARGETS.items():
        print("=" * 70)
        print(f"ADDRESS: {addr}  [{label}]")
        print("-" * 70)

        # Basic account type
        contract = is_contract(addr)
        usdt_bal = usdt_balance(addr)
        bnb_bal  = bnb_balance(addr)
        print(f"  Type       : {'CONTRACT' if contract else 'EOA (plain wallet)'}")
        print(f"  USDT bal   : {usdt_bal:,.2f}" if usdt_bal is not None else "  USDT bal   : unknown")
        print(f"  BNB bal    : {bnb_bal:.4f}" if bnb_bal is not None else "  BNB bal    : unknown")

        # Inflows
        inflows = transfers_to(addr, lo, cur)
        in_by_src = {}
        for f, t, a in inflows:
            if a > 0: in_by_src[f] = in_by_src.get(f, 0) + a
        total_in = sum(in_by_src.values())
        print(f"\n  INFLOWS  total={total_in:,.0f} USDT from {len(in_by_src)} sources:")
        for src, amt in sorted(in_by_src.items(), key=lambda x: -x[1])[:10]:
            print(f"    {src}  {amt:>12,.0f}  [{classify(src)}]")

        # Outflows
        outflows = transfers_from(addr, lo, cur)
        out_by_dst = {}
        for f, t, a in outflows:
            if a > 0: out_by_dst[t] = out_by_dst.get(t, 0) + a
        total_out = sum(out_by_dst.values())
        print(f"\n  OUTFLOWS total={total_out:,.0f} USDT to {len(out_by_dst)} destinations:")
        for dst, amt in sorted(out_by_dst.items(), key=lambda x: -x[1])[:10]:
            c = classify(dst)
            print(f"    {dst}  {amt:>12,.0f}  [{c}]")

        # Second hop: for each top destination that's still unknown, follow one more hop
        print(f"\n  SECOND-HOP (top unknown destinations):")
        traced = 0
        for dst, amt in sorted(out_by_dst.items(), key=lambda x: -x[1])[:5]:
            c = classify(dst)
            if "unknown" not in c: continue
            hop2_out = {}
            for f2, t2, a2 in transfers_from(dst, lo, cur):
                if a2 > 0: hop2_out[t2] = hop2_out.get(t2, 0) + a2
            if hop2_out:
                top = sorted(hop2_out.items(), key=lambda x: -x[1])[:3]
                for h2dst, h2amt in top:
                    h2c = classify(h2dst)
                    print(f"    {dst[:20]}… -> {h2dst}  {h2amt:>10,.0f}  [{h2c}]")
            else:
                print(f"    {dst[:20]}…  (no outbound USDT in window)")
            traced += 1
            if traced >= 3: break

        print()

if __name__ == "__main__":
    main()
