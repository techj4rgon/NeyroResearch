#!/usr/bin/env python3
"""One-off probe: did the position get burned / migrated to a new range, or drained out?
Scans Mint AND Burn events on the pool across ALL tick ranges over the lookback window,
plus current pool liquidity. Read-only."""
import json, urllib.request, time
from decimal import Decimal, getcontext
getcontext().prec=80
RPCS=["https://bsc-rpc.publicnode.com","https://bsc.drpc.org"]
POOL="0x92b7807bf19b7dddf89b706143896d05228f3121".lower()
MINT="0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde"
BURN="0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c"
COLLECT="0x70935338e69775456a85ddef226c395fb668b63fa0115f5f20610b388e6ca9c0"
LOOKBACK=70000; CHUNK=10000
def _post(u,m,p,t=24):
    pl=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    try:
        req=urllib.request.Request(u,data=pl,headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req,timeout=t) as r: return json.loads(r.read()).get("result")
    except Exception: return None
def rpc(m,p,retries=4):
    for _ in range(retries):
        for u in RPCS:
            r=_post(u,m,p)
            if r is not None: return r
        time.sleep(0.4)
    return None
def s24(v): return v-(1<<24) if v>=(1<<23) else v
def scan(topic0, amount_word):
    cur=int(rpc("eth_blockNumber",[]),16); lo=cur-LOOKBACK; b=lo; agg={}
    while b<=cur:
        e=min(b+CHUNK-1,cur)
        r=rpc("eth_getLogs",[{"address":POOL,"topics":[topic0],"fromBlock":hex(b),"toBlock":hex(e)}])
        if isinstance(r,list):
            for lg in r:
                tl=s24(int(lg["topics"][2],16)); tu=s24(int(lg["topics"][3],16))
                d=lg["data"][2:]; w=[d[i:i+64] for i in range(0,len(d),64)]
                amt0=int(w[amount_word],16)/1e18
                k=(tl,tu); agg[k]=agg.get(k,0)+amt0
        b=e+1
    return agg,cur,lo

# current pool state
slot0=rpc("eth_call",[{"to":POOL,"data":"0x3850c7bd"},"latest"])
w0=[slot0[2:][i:i+64] for i in range(0,len(slot0[2:]),64)]
cur_tick=s24(int(w0[1],16))
liq=rpc("eth_call",[{"to":POOL,"data":"0x1a686502"},"latest"])  # liquidity()
active_liq=int(liq,16) if isinstance(liq,str) else None
print(f"current tick = {cur_tick}   active in-range liquidity = {active_liq:,}" if active_liq is not None else f"tick={cur_tick}")

print("\n=== MINTS by tick range (amount0/USDT side) ===")
m,cur,lo=scan(MINT,2)
for k,v in sorted(m.items(),key=lambda x:-x[1]):
    print(f"  ticks {k[0]:>8} .. {k[1]:>8}   {v:,.0f}")

print("\n=== BURNS by tick range (amount0/USDT side) ===")
bn,_,_=scan(BURN,1)
for k,v in sorted(bn.items(),key=lambda x:-x[1]):
    print(f"  ticks {k[0]:>8} .. {k[1]:>8}   {v:,.0f}")
print(f"\nwindow blocks {lo}..{cur}  (~{(cur-lo)*0.45/3600:.1f}h)")
