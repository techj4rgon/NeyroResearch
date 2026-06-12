# Neyro/Aurum daily health-check guide (for a routine reading watch_simple.py)

## What you're monitoring
`watch_simple.py` is a read-only, on-chain (BSC) scanner for the Neyro / Aurum
"Neyro AI" yield platform. Prior forensic work concluded the platform is
**structurally a Ponzi**: there is no on-chain evidence of real trading yield, user
payouts are funded by new user deposits, and surplus is swept one-way to Binance.

So this is **not** an "is it healthy?" check in the investment sense. Each day you are
checking three things:
1. **Still behaving like a Ponzi?** (confirmation / steady-state)
2. **Signs of imminent collapse?** (reserve draining, deposits drying up)
3. **Any anomaly that would CHALLENGE the Ponzi conclusion?** (external capital
   minting into the position, or funds returning from Binance) — these are the
   surprising signals worth flagging loudly.

## What the script prints each run (six blocks + a VERDICT line)
The script scans roughly the **last ~9 hours** of chain and prints:

- `[MINT]   X USDT entered the position via N mints ... internal: A | EXTERNAL: B`
  Capital added to the platform's liquidity position (ticks 45000–46054).
  `internal` = added by the operator bot from the deposit funnel. `EXTERNAL` = added
  by some address that is NOT the bot/cluster (and isn't just relaying funnel money).
- `[DEPOSIT]  X USDT user deposits into funnel` + a `deposit/mint coverage` %.
  New user money entering the system.
- `[SWEEP]   X USDT left pool via collects, N recipients` (+ any flagged sinks).
  Money leaving the position. May flag `NEW UNKNOWN SINK` (an unrecognized address
  that pulled funds out) or `known CEX route` (heading to Binance).
- `[RESERVE]  platform position holds X USDT now (pool tick T)`.
  **The single most important number.** Absolute USDT parked in the position, read
  from pool tick state. This is the "tank level."
- `[POSITION] window flow: mints IN - collects OUT = NET (grew/drew down)`.
  Net change to the position over the ~9h window.
- `[RETURN]   Binance -> cluster: direct X + indirect Y USDT`.
  Money flowing BACK from known Binance wallets into the platform cluster.
- `VERDICT:` the script's own one-line read.

## How to read each signal

| Signal | NEGATIVE / Ponzi-consistent (expected) | POSITIVE / would CHALLENGE Ponzi (flag loudly) |
|---|---|---|
| **EXTERNAL mint** | `EXTERNAL: 0` — position fed only by the operator bot from deposits. Pure recycling. | **`EXTERNAL > ~$1k`** — an outside address minted real capital into the position. Strongest "maybe not a pure Ponzi" signal. **FLAG + report the address.** |
| **RETURN** | `0` — nothing comes back; extraction is one-way. | **`RETURN > 0`** — capital returned from Binance into the cluster. Suggests funds cycling back (possible real treasury/trading). **FLAG + report amount/source.** |
| **RESERVE** (tank) | Stable, or slowly drifting. Historically ~$0.94M–$1.19M. | Rising **while** payouts exceed deposits → external top-up. **FLAG.** |
| **RESERVE — collapse risk** | — | **Falling steadily day over day** → tank draining. Estimate runway and **FLAG as collapse risk.** |
| **DEPOSIT** | Steady inflow (~$550k/9h typical). | **Sharp drop (>30% vs recent days)** → new money drying up; classic pre-collapse Ponzi signal. **FLAG.** |
| **POSITION net** | Mildly negative/flat; replenished by recycled deposits. | Strongly negative repeatedly **and** reserve falling → paying out faster than topping up. **FLAG.** |
| **SWEEP** | Ongoing collects; periodic sweep to the known Binance route. Expected one-way extraction. | A **new, large, unrecognized sink** that then forwards to a CEX → note and watch (could be a new off-ramp). |

## Baseline reference numbers (per ~9h run, for spotting deviations)
- Reserve: **~$0.94M – $1.19M** (was ~$1.147M at last check).
- User deposits into funnel: **~$550k–570k**.
- Mints into position: **~$320k, 100% internal** (operator bot).
- Collects out: **~$540k–550k**.
- Position net: **~ −$200k to −$230k** (window-level; noisy — judge drawdown by the
  RESERVE trend across days, NOT by a single window's net).
- EXTERNAL and RETURN: **historically $0.** Any nonzero value is the headline.
- Known benign sink `0x46c2abb69c9a91a86352e11b7ed4bce56a9998aa` (~$10k, parked, looks
  like an ordinary user wallet) — **do not** treat as an alert unless it grows a lot
  or forwards onward to a CEX.

## Day-over-day (important — the script is stateless)
The script does not remember anything between runs. For the trend signals to work,
**the routine must record each day's `RESERVE` and `DEPOSIT` numbers and compare to
prior days.** Specifically:
- Track `RESERVE` daily → if it's on a clear multi-day downtrend, compute
  `runway_days = current_reserve / average_daily_reserve_decline` and flag it.
- Track `DEPOSIT` daily → flag a sustained drop (new money slowing).

## Daily health-check output the routine should produce
Produce a short report with:
1. **Headline status**, one of:
   - `STABLE PONZI PASS-THROUGH` (reserve steady, deposits steady, mints all-internal, no return)
   - `DRAINING — COLLAPSE RISK` (reserve trending down / deposits falling; include runway estimate)
   - `ANOMALY — EXTERNAL CAPITAL` (EXTERNAL mint > 0)
   - `ANOMALY — RETURN FLOW` (RETURN > 0)
2. **Key numbers**: reserve today vs prior day (Δ), deposits, position net, EXTERNAL, RETURN.
3. **Flags**: any row above that tripped, with the relevant address/amount.
4. **One-line takeaway** in plain language.

## Suggested routine prompt
> Run `python3 watch_simple.py` (Windows: via the run.cmd wrapper) and read its output.
> Using HEALTH_CHECK_GUIDE.md, produce a daily health check: a headline status, the key
> numbers (and the change in RESERVE and DEPOSIT vs the value you recorded yesterday),
> any tripped flags with addresses/amounts, and a one-line takeaway. Record today's
> RESERVE and DEPOSIT figures so you can compare tomorrow. If EXTERNAL mint > 0 or
> RETURN > 0, put that at the very top and include the address(es).

## Caveats (state these in the report when relevant)
- On-chain only: cannot see CEX-internal activity, off-exchange OTC, or non-BSC chains.
  "No return on BSC/USDT" is not a categorical "nothing came back."
- One daily run samples ~9h of 24h. Good for the RESERVE trend and structural signals;
  the EXTERNAL/RETURN tripwires are more reliable the more often the script runs.
- RESERVE math assumes the pool price stays below the position range (tick < 45000);
  if `[RESERVE] unavailable` appears, note it rather than treating it as $0.
- This is monitoring, not financial or legal advice.
