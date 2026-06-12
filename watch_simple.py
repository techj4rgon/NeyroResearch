#!/usr/bin/env python3
"""
Neyro/Aurum watch -- SINGLE FILE, STATELESS. For Windows Task Scheduler / cron.

Each run scans the last ~9h and prints one VERDICT plus details.

Checks (in order of how much they matter for "is this a Ponzi?"):
  MINT   : capital entering the platform position (mints at ticks 45000-46054),
           split by funder -> INTERNAL (deposit funnel/operator bot) vs EXTERNAL.
           This is ORIGIN-AGNOSTIC: real outside money topping up the position
           shows here no matter what CEX/chain/asset it came through.
  DEPOSIT: user deposits into the funnel, to reconcile against MINT.
  SWEEP  : USDT leaving the pool via platform-tick collects; flags new sinks.
  RETURN : USDT coming back FROM known Binance wallets into the cluster (BSC/USDT
           only -- a narrow bonus signal, not the primary test).

No files, no state, no git. Pure Python 3 stdlib.
"""
import json, urllib.request, time, datetime
from decimal import Decimal, getcontext
getcontext().prec=80
RPCS=["https://bsc-rpc.publicnode.com","https://bsc.drpc.org"]
USDT="0x55d398326f99059ff775485246999027b3197955"
POOL="0x92b7807bf19b7dddf89b706143896d05228f3121".lower()
NPM="0x46a15b0b27311cedf172ab29e4f4766fbe7f4364"          # Pancake V3 position mgr
BOT="0x8b45cda448cc26e7f55ef3e77374c7cae8199b61"          # operator bot
FUNNEL="0xe197f1229f7625d74780f1f6be2b9552566fa1e0"       # deposit funnel
TS="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"  # Transfer
COLLECT="0x70935338e69775456a85ddef226c395fb668b63fa0115f5f20610b388e6ca9c0"
MINT="0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde"  # PancakeV3 (NOT canonical uniV3 bae)
TL="0x"+format(45000,'064x'); TU="0x"+format(46054,'064x')   # platform tick range
LOOKBACK=70000; CHUNK=10000
SWEEP_MIN=10000.0; RET_MIN=50000.0; MINT_MIN=1.0; MAXTRACE=8
def pad(a): return "0x"+"0"*24+a[2:].lower()
CLUSTER={
 FUNNEL:"funnel",BOT:"bot",
 "0x42c8d37f4f4d0ec6644248d515d7fc849a2a5f61":"collector","0x1a2755eb8f2caee1e69aed75e9de6328fef3488e":"relay",
 "0xc105000dd757d00103e0fb18f0c9ed1a8030fe6b":"hub","0xb16cd608ec3f751f2f316ead1f7601131bbf0400":"distributor",
 "0xa02c3b70339730368a9eb6f168124171baa38365":"passthrough"}
INTERNAL_MINTERS=set(CLUSTER)|{NPM}
SWEEP_ROUTE={"0x233c5370ccfb3cd7409d9a3fb98ab94de94cb4cd":"CEX-routing processor",
 "0x5a8e12d1f7148886fe35f6fa04f5a2c2b60ac354":"sweep-hop","0x884c7f4778bb1831a7f2691c194cd51e9644f60e":"Binance deposit",
 "0x88bbcaeeaf0dca4ad50e8aab9387cd78c60be758":"Binance deposit"}
BINANCE={"0x8894e0a0c962cb723c1976a4421c95949be2d4e3":"Binance 51","0xe2fc31f816a9b94326492132018c3aecc4a93ae1":"Binance",
 "0x515b72ed8a97f42c568d6a143232775018f133c8":"Binance","0x161ba15a5f335c9f06bb5bbb0a9ce14076fbb645":"Binance",
 "0xf977814e90da44bfa03b6295a0616a897441acec":"Binance 8","0x29bdfbf7d27462a2d115748ace2bd71a2646946c":"Binance 16",
 "0x3c783c21a0383057d128bae431894a5c19f9cf06":"Binance","0x835678a611b28684005a5e2233695fb6cbbb0007":"Binance"}
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
def btime(b):
    h=rpc("eth_getBlockByNumber",[hex(b),False]); return int(h["timestamp"],16) if isinstance(h,dict) else None
def scan_logs(params):
    out=[]; lo=params["_lo"]; hi=params["_hi"]; b=lo
    while b<=hi:
        e=min(b+CHUNK-1,hi)
        q=dict(params); q.pop("_lo"); q.pop("_hi"); q["fromBlock"]=hex(b); q["toBlock"]=hex(e)
        r=rpc("eth_getLogs",[q])
        if isinstance(r,list): out+=r
        b=e+1
    return out
def transfers(addr,pos,lo,hi):
    t=[TS,None,None]; t[pos]=pad(addr); out=[]
    for lg in scan_logs({"address":USDT,"topics":t,"_lo":lo,"_hi":hi}):
        out.append(("0x"+lg["topics"][1][26:].lower(),"0x"+lg["topics"][2][26:].lower(),int(lg["data"],16)/1e18))
    return out
def cls(a):
    a=(a or "").lower()
    if a in CLUSTER: return "cluster:"+CLUSTER[a]
    if a==POOL: return "pool"
    if a in BINANCE: return "BINANCE:"+BINANCE[a]
    if a in SWEEP_ROUTE: return "SWEEP:"+SWEEP_ROUTE[a]
    return "unknown"
def top_dest(addr,lo,hi):
    d={}
    for f,t,a in transfers(addr,1,lo,hi):
        if a>0: d[t]=d.get(t,0)+a
    if not d: return None,0
    k=max(d,key=d.get); return k,d[k]
def top_src(addr,lo,hi):
    d={}
    for f,t,a in transfers(addr,2,lo,hi):
        if a>0: d[f]=d.get(f,0)+a
    if not d: return None,0
    k=max(d,key=d.get); return k,d[k]

def s24(v): return v-(1<<256) if v>=(1<<255) else v
def parked_reserve():
    """USDT parked by the single-sided out-of-range position at tick 45000.
    Read straight from pool tick state; valid while current tick < 45000."""
    slot0=rpc("eth_call",[{"to":POOL,"data":"0x3850c7bd"},"latest"])
    if not isinstance(slot0,str): return None,None
    w0=[slot0[2:][i:i+64] for i in range(0,len(slot0[2:]),64)]
    cur_tick=s24(int(w0[1],16))
    r=rpc("eth_call",[{"to":POOL,"data":"0xf30dba93"+format(45000,"064x")},"latest"])
    if not isinstance(r,str) or cur_tick>=45000: return None,cur_tick
    L=int(r[2:66],16)
    sq=lambda t:int((Decimal("1.0001")**(Decimal(t)/2))*(Decimal(2)**96))
    sA=sq(45000);sB=sq(46054)
    amt0=(Decimal(L)*(Decimal(2)**96)*Decimal(sB-sA))/(Decimal(sB)*Decimal(sA))
    return float(amt0/Decimal(10**18)),cur_tick

def main():
    cur=int(rpc("eth_blockNumber",[]),16); lo=cur-LOOKBACK
    tc=btime(cur) or int(time.time()); tlo=btime(lo)
    f=lambda ts: datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).strftime('%m-%d %H:%M') if ts else "?"
    print("="*62); print("NEYRO/AURUM WATCH", datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'))
    print(f"window {f(tlo)} -> {f(tc)} UTC  (~{(cur-lo)*0.45/3600:.1f}h)"); print("="*62)
    alerts=[]

    # ---- MINT: capital entering the platform position (origin-agnostic) ----
    mints=[]
    for lg in scan_logs({"address":POOL,"topics":[MINT,None,TL,TU],"_lo":lo,"_hi":cur}):
        d=lg["data"][2:]; w=[d[i:i+64] for i in range(0,len(d),64)]
        usdt=int(w[2],16)/1e18
        if usdt>0: mints.append((usdt,lg["transactionHash"]))
    mint_total=sum(m[0] for m in mints)
    internal=0.0; external=0.0; ext_detail=[]; txfrom={}; traced=0
    for usdt,txh in sorted(mints,key=lambda x:-x[0]):
        if usdt<MINT_MIN: continue
        frm=txfrom.get(txh)
        if frm is None and traced<MAXTRACE:
            tx=rpc("eth_getTransactionByHash",[txh]); frm=((tx or {}).get("from") or "").lower(); txfrom[txh]=frm; traced+=1
        if frm and frm in INTERNAL_MINTERS:
            internal+=usdt
        elif frm:
            # external initiator: where did IT get the USDT? one hop
            s,sv=top_src(frm,lo,cur); sc=cls(s)
            if s in INTERNAL_MINTERS:
                internal+=usdt   # just relaying funnel money
            else:
                external+=usdt; ext_detail.append((frm,usdt,s,sc))
        else:
            internal+=usdt  # untraced (beyond MAXTRACE) -> assume internal, note below
    print(f"\n[MINT] {mint_total:,.0f} USDT entered the position via {len(mints)} mints at platform ticks")
    print(f"       internal (funnel/bot): {internal:,.0f}   |   EXTERNAL: {external:,.0f}")
    for frm,usdt,s,sc in ext_detail[:5]:
        print(f"       *** EXTERNAL MINT {usdt:,.0f} by {frm}  funded from {s} ({sc}) ***")
    if external>max(1000.0,0.05*max(mint_total,1)): alerts.append(f"EXTERNAL-CAPITAL {external:,.0f}")

    # ---- DEPOSIT: user inflow into funnel (reconcile vs mint) ----
    dep=0.0
    for fr,t,a in transfers(FUNNEL,2,lo,cur):
        if a>0 and fr not in CLUSTER: dep+=a
    print(f"\n[DEPOSIT] user deposits into funnel: {dep:,.0f} USDT")
    if mint_total>0:
        cover = dep/mint_total
        print(f"          deposit/mint coverage: {cover*100:,.0f}%  "
              + ("(mints exceed deposits -> capital from elsewhere)" if cover<0.85 else "(mints ~covered by deposits)"))

    # ---- SWEEP: collects leaving pool at platform ticks ----
    rec={}
    for lg in scan_logs({"address":POOL,"topics":[COLLECT,None,TL,TU],"_lo":lo,"_hi":cur}):
        d=lg["data"][2:]; w=[d[i:i+64] for i in range(0,len(d),64)]
        r="0x"+w[0][24:].lower(); a=int(w[1],16)/1e18
        rec[r]=rec.get(r,0)+a
    collect_total=sum(rec.values())
    print(f"\n[SWEEP] {collect_total:,.0f} USDT left pool via platform collects, {len(rec)} recipients")
    traced=0
    for r,amt in sorted(rec.items(),key=lambda x:-x[1]):
        if amt<SWEEP_MIN: break
        c=cls(r)
        if c.startswith("cluster") or c=="pool": continue
        if c.startswith(("SWEEP","BINANCE")):
            print(f"   {r} {amt:,.0f}  -> known CEX route ({c.split(':')[1]})"); alerts.append(f"sweep->Binance {amt:,.0f}"); continue
        if traced<MAXTRACE:
            dk,dv=top_dest(r,lo,cur); traced+=1; dc=cls(dk) if dk else ""
            if dc.startswith(("BINANCE","SWEEP")):
                print(f"   {r} {amt:,.0f}  -> {dk} ({dc.split(':')[1]}) [CEX]"); alerts.append(f"sweep->CEX {amt:,.0f}")
            elif dk and (dk in CLUSTER or dk==POOL):
                print(f"   {r} {amt:,.0f}  -> recirculates")
            else:
                print(f"   {r} {amt:,.0f}  -> {dk}  *** NEW UNKNOWN SINK - REVIEW ***"); alerts.append(f"new sink {r} {amt:,.0f}")

    # ---- position reserve (absolute) + net flow (window) ----
    reserve,ctick=parked_reserve()
    net=mint_total-collect_total
    if reserve is not None:
        print(f"\n[RESERVE] platform position holds {reserve:,.0f} USDT now (pool tick {ctick}).")
        print(f"          ^ watch this number across runs: falling = tank draining,"
              f" flat while payouts>deposits = external top-up.")
    else:
        print(f"\n[RESERVE] unavailable (pool tick {ctick} may have entered the position range).")
    print(f"[POSITION] window flow: mints {mint_total:,.0f} in - collects {collect_total:,.0f} out = {net:,.0f}  "
          + ("(grew)" if net>0 else "(drew down)"))

    # ---- RETURN: Binance -> cluster (narrow bonus signal) ----
    inflow={}
    for addr in CLUSTER:
        for fr,t,a in transfers(addr,2,lo,cur):
            if a>0 and fr not in CLUSTER: inflow[fr]=inflow.get(fr,0)+a
    direct=sum(v for k,v in inflow.items() if k in BINANCE)
    indirect=0.0; traced=0
    for s,v in sorted(inflow.items(),key=lambda x:-x[1]):
        if s in BINANCE or v<RET_MIN or traced>=MAXTRACE: continue
        ss={}
        for fr,t,a in transfers(s,2,lo,cur):
            if a>0: ss[fr]=ss.get(fr,0)+a
        traced+=1; tot=sum(ss.values()); binv=sum(x for k,x in ss.items() if k in BINANCE)
        if tot and binv/tot>=0.30: indirect+=v
    print(f"\n[RETURN] Binance -> cluster (BSC/USDT only): direct {direct:,.0f} + indirect {indirect:,.0f} USDT")
    if direct+indirect>1: alerts.append(f"RETURN {direct+indirect:,.0f}")

    # ---- VERDICT ----
    print("\n"+"-"*62)
    drew = (net<0)
    if external>max(1000.0,0.05*max(mint_total,1)):
        print(f"VERDICT: *** EXTERNAL CAPITAL ENTERING POSITION ({external:,.0f} USDT) - an outside")
        print("         address minted into the position. This is the real-funding signal; trace it.")
    elif any(x.startswith("RETURN") for x in alerts):
        print("VERDICT: *** RETURN FLOW from Binance into cluster - reopens trading theory; trace it.")
    else:
        # normal case: all mints operator-internal (recycled deposits)
        tag = "drawing down" if drew else "holding/growing"
        print(f"VERDICT: position fed only by operator bot from deposits (no external capital),")
        print(f"         {tag} this window (net {net:,.0f}), no Binance return. Consistent with Ponzi.")
        extra=[a for a in alerts if a.startswith("new sink")]
        if extra: print("         note: "+" | ".join(extra)[:90])
    print("-"*62)

if __name__=="__main__": main()
