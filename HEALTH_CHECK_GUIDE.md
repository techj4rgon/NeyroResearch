# Neyro/Aurum daily health-check guide

**Purpose: follow the money and look for evidence of real trading.** Tools:
`record_stats.py` (runs `watch_simple.py`, appends to `daily_stats.csv`) and
`probe_migration.py` (Burns/Mints across all tick ranges). Read this whole guide each run.

## What you're monitoring
`watch_simple.py` is a read-only, on-chain (BSC) scanner for the Neyro / Aurum
"Neyro AI" yield platform. Prior forensic work concluded the platform is
**structurally a Ponzi**: there is no on-chain evidence of real trading yield, user
payouts are funded by new user deposits, and surplus is swept one-way to Binance.

So this is **not** an "is it healthy?" check in the investment sense. Each day you are
checking four things:
1. **Still behaving like a Ponzi?** (confirmation / steady-state)
2. **Signs of imminent collapse / EXIT?** (reserve drained AND swept to Binance, deposits drying up)
3. **Any anomaly that would CHALLENGE the Ponzi conclusion?** (external capital
   minting into the position, or funds returning from Binance) — these are the
   surprising signals worth flagging loudly.
4. **Is a big reserve move a teardown/rebuild or a real exit?** A sharp RESERVE
   drop (even to $0) is ambiguous: the operators routinely **burn** the whole
   liquidity position and **re-mint** a new one in the *same* range as part of normal
   workflow changes. Do **not** call "collapse" off the RESERVE number alone — you must
   look at the on-chain Burn/Mint events to tell a rebuild apart from an exit (see below).

## IMPORTANT: RESERVE = 0 (or a big drop) is NOT automatically a collapse
The RESERVE number is read point-in-time from pool tick state, so it goes to $0 the
instant the position is burned — *even if it is re-minted seconds later in the same
block range.* On 2026-06-14 the reserve read $6.06M then $0 within ~5h; the Burn/Mint
logs showed the $6.06M position was **burned and ~$434k re-minted into the identical
tick range (45000–46054), same pool** — a **rebuild in place**, not an exit. Three
distinct explanations for a reserve crash, and you MUST distinguish them with
`probe_migration.py`:

| Pattern (from Burn/Mint logs) | What it means |
|---|---|
| Burn of old range **+ re-mint into the SAME range** (45000–46054), deposits still flowing | **REBUILD IN PLACE** — workflow change, benign-ish. Not a collapse. |
| Burn of old range **+ new mints in a DIFFERENT range or pool** | **MIGRATION** — track the new range/pool; update the script's TL/TU. |
| Burn **+ collected funds routed to Binance, deposits stop** | **EXIT / COLLAPSE** — the real alarm. Flag loudly. |
| Burn with **no re-mint and funds sitting uncollected** | **UNWINDING** — watch where the tokensOwed go next run. |

## THE CORE PURPOSE: follow the money, look for evidence of real trading
Everything else is in service of one question: **does any real trading yield exist, or
is every dollar paid out just a recycled dollar from a newer depositor?** The Ponzi
conclusion holds *until* the money trail shows otherwise. Each run, actually trace the
flows — do not just read the summary numbers.

### The money trail (what feeds what)
```
   new USER deposits ──▶ FUNNEL (0xe197f1…) ──▶ operator BOT (0x8b45cd…)
                                                      │
                                                      ▼  mint (always "internal")
                                          PancakeV3 POOL position (ticks 45000–46054)
                                                      │  collect / burn
                                                      ▼
                            cluster wallets (collector/relay/hub/distributor/passthrough)
                               │                                   │
                               ▼ recirculate                       ▼ sweep
                        back to depositors                  CEX route ──▶ BINANCE
                        (pays "yield")                       (one-way extraction)
```
Pure-Ponzi signature: **deposits in ≈ payouts out**, mints are 100% internal, surplus
goes one-way to Binance, and **nothing of value ever comes back** (no return, no
external capital, no position that grew on its own).

### What WOULD be evidence of real trading (flag any of these LOUDLY)
These are the surprises that would break the Ponzi conclusion — hunt for them:
1. **EXTERNAL mint > ~$1k** — capital entering the position from a non-cluster address.
   Real outside money taking a position. Report the address + its funding source.
2. **RETURN > 0** (Binance → cluster) — money coming *back* from the CEX. Pure
   extraction never returns; a return suggests a treasury actually trading off-exchange.
3. **Reserve / position growing without matching deposits** — value created somewhere
   other than new depositors. Compute `deposits − (mints + payouts)`: a persistent
   positive surplus that *stays in* the system (not swept) needs an explanation.
4. **Collects/burn proceeds exceeding the deposits that funded them, repeatedly** —
   paying out more than came in, sustained, *without* the reserve draining → money is
   coming from somewhere real. (One window is noise; a multi-day pattern is the signal.)
5. **Proceeds routed to a DEX/trading venue or a market-making contract** (not just
   recirculation or Binance deposit wallets) — would show funds actually being traded.
6. **A new sink that forwards onward to a trading venue** rather than to a CEX deposit
   address or back into the cluster.

If you see none of these (the normal case), state plainly: *"No evidence of trading;
flows are consistent with deposit recycling."* If you see any, that goes at the TOP of
the report with addresses and amounts, and the headline becomes
`ANOMALY — POSSIBLE TRADING`.

### How to actually follow the money each run
- **Reconcile the window:** deposits vs mints (coverage %), and burn/collect proceeds vs
  where they went. Money that enters but doesn't leave (or leaves but wasn't deposited)
  is the interesting residual — chase it.
- **Trace the biggest movers:** for the largest collect recipients and any burn
  proceeds, follow one or two hops (the script's `top_dest`/`top_src` helpers, or by
  hand) to classify the endpoint: recirculate / Binance / new sink / trading venue.
- **Account for burns:** when `probe_migration.py` shows a big burn, the burned USDT
  must go *somewhere* — collected then recirculated, collected then swept, or left as
  tokensOwed. Don't let a multi-million-dollar burn drop off the ledger; carry the
  unaccounted remainder to the next day and close it.
- **Expand the lens when needed:** the hardcoded addresses (BINANCE, SWEEP_ROUTE,
  CLUSTER) and tick range (45000–46054) are a snapshot of a moving target. If flows go
  to addresses you can't classify, or mints appear in a new range, **widen the search
  and update the address lists / ticks** rather than dismissing it as noise. Following
  the money takes priority over staying inside the script's current assumptions.

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

### Extra probe (run when RESERVE moves a lot, and ideally every day)
`watch_simple.py` only scans Mints/Collects at the hardcoded platform ticks
(45000–46054) and does **not** track Burns or migration to other ranges. So whenever
RESERVE drops sharply (or jumps), run:

    python3 probe_migration.py

It scans **Mint AND Burn events across ALL tick ranges** on the pool plus current
liquidity, and prints USDT totals per `(tickLower, tickUpper)`. Use it to answer:
- Was the old position **burned**? (look for a large Burn at 45000–46054)
- Was it **re-minted in the same range** (rebuild) or a **different range/pool** (migration)?
- **Burn-vs-collect gap:** compare the Burn total to the `[SWEEP]` collect total. A big
  burn with small collects means USDT is sitting as uncollected `tokensOwed` (or was
  collected just outside the window). Track that gap day-over-day — if it later
  collects and routes to Binance, that is the exit signal.
- Ignore tick ranges shown as huge `115792089...` numbers — those are negative ticks
  near the current price and are immaterial noise.

## How to read each signal

| Signal | NEGATIVE / Ponzi-consistent (expected) | POSITIVE / would CHALLENGE Ponzi (flag loudly) |
|---|---|---|
| **EXTERNAL mint** | `EXTERNAL: 0` — position fed only by the operator bot from deposits. Pure recycling. | **`EXTERNAL > ~$1k`** — an outside address minted real capital into the position. Strongest "maybe not a pure Ponzi" signal. **FLAG + report the address.** |
| **RETURN** | `0` — nothing comes back; extraction is one-way. | **`RETURN > 0`** — capital returned from Binance into the cluster. Suggests funds cycling back (possible real treasury/trading). **FLAG + report amount/source.** |
| **RESERVE** (tank) | Stable, or slowly drifting. (Has ranged ~$0.94M up to ~$6M; see regime note below.) | Rising **while** payouts exceed deposits → external top-up. **FLAG.** |
| **RESERVE — sharp drop / $0** | A single-window crash is **ambiguous, not automatically collapse.** Run `probe_migration.py` first. | Only call **COLLAPSE/EXIT** if the burn is **not** re-minted AND funds route to Binance AND deposits stop. A burn + re-mint in the same range = **REBUILD** (note it, don't cry collapse). |
| **RESERVE — slow bleed** | — | **Falling steadily day over day with no rebuild** → tank draining. Estimate runway and **FLAG as collapse risk.** |
| **BURN** (from probe) | No large burns, or burn immediately re-minted in the same range. | Large burn (≈ prior reserve) → identify the pattern in the table above; report burn amount, whether re-minted, and the burn-vs-collect gap. |
| **DEPOSIT** | Steady inflow (~$550k/9h typical). | **Sharp drop (>30% vs recent days)** → new money drying up; classic pre-collapse Ponzi signal. **FLAG.** |
| **POSITION net** | Mildly negative/flat; replenished by recycled deposits. | Strongly negative repeatedly **and** reserve falling → paying out faster than topping up. **FLAG.** |
| **SWEEP** | Ongoing collects; periodic sweep to the known Binance route. Expected one-way extraction. | A **new, large, unrecognized sink** that then forwards to a CEX → note and watch (could be a new off-ramp). |

## Baseline reference numbers (per ~9h run, for spotting deviations)
- Reserve: original baseline **~$0.94M – $1.19M**; then a **regime change 06-12→06-14**
  where reserve climbed $1.1M → $6.06M before a burn/rebuild. Treat the baseline as
  shifting — anchor on the *trend and the burn/mint logs*, not a fixed band.
- User deposits into funnel: **~$550k–570k** originally; spiked to **~$1.2M** by 06-14.
- Mints into position: **~$320k–474k, 100% internal** (operator bot).
- Collects out: **~$540k–550k** originally; spiked to **~$1.33M** on the burn day.
- Position net: **~ −$200k to −$230k** typically (window-level; noisy — judge drawdown
  by the RESERVE trend across days, NOT by a single window's net).
- EXTERNAL and RETURN: **historically $0.** Any nonzero value is the headline. (One
  indirect RETURN of $53,800 appeared 06-13 — the kind of blip to watch, not yet a trend.)
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
   - `POSITION REBUILD IN PLACE` (big burn re-minted into the SAME range; not a collapse — say so explicitly)
   - `MIGRATION` (position moved to a new range/pool — give the new ticks/pool)
   - `DRAINING — COLLAPSE RISK` (reserve trending down with no rebuild / deposits falling; include runway estimate)
   - `EXIT IN PROGRESS` (large burn → collects routed to Binance AND deposits stopping)
   - `ANOMALY — EXTERNAL CAPITAL` (EXTERNAL mint > 0)
   - `ANOMALY — RETURN FLOW` (RETURN > 0)
   - `ANOMALY — POSSIBLE TRADING` (any concrete evidence of real yield; see "evidence of trading" below)
2. **Key numbers**: reserve today vs prior day (Δ), deposits, mints (internal/external),
   collects, position net, **burn total + burn-vs-collect gap**, EXTERNAL, RETURN.
3. **Follow-the-money line**: trace the largest flows end to end this window — where did
   deposits go, where did collects/burn proceeds go (recirculate? CEX? new sink?).
4. **Evidence-of-trading check**: explicitly state whether anything this window looks
   like real trading yield vs. pure deposit recycling (see section below). Default is "no."
5. **Flags**: any row above that tripped, with the relevant address/amount.
6. **One-line takeaway** in plain language.

## Suggested routine prompt
> Run `python3 record_stats.py` (runs watch_simple.py and appends to daily_stats.csv),
> then `python3 probe_migration.py` to capture Burns/Mints across all tick ranges.
> Using HEALTH_CHECK_GUIDE.md, produce a daily health check whose PURPOSE is to follow
> the money and look for evidence of real trading. Include: a headline status; the key
> numbers (RESERVE and DEPOSIT vs yesterday's recorded values, plus mints
> internal/external, collects, burn total and the burn-vs-collect gap); a
> follow-the-money line tracing the largest flows end to end; an explicit
> evidence-of-trading verdict (default "none — consistent with recycling"); any tripped
> flags with addresses/amounts; and a one-line takeaway. Provide a visual map of the
> connections and numbers. If RESERVE dropped sharply, use probe_migration.py to decide
> REBUILD vs MIGRATION vs EXIT before saying "collapse." If EXTERNAL mint > 0, RETURN > 0,
> or anything looks like real trading, put it at the very top with the address(es).

## Caveats (state these in the report when relevant)
- On-chain only: cannot see CEX-internal activity, off-exchange OTC, or non-BSC chains.
  "No return on BSC/USDT" is not a categorical "nothing came back."
- One daily run samples ~9h of 24h. Good for the RESERVE trend and structural signals;
  the EXTERNAL/RETURN tripwires are more reliable the more often the script runs.
- RESERVE math assumes the pool price stays below the position range (tick < 45000);
  if `[RESERVE] unavailable` appears, note it rather than treating it as $0.
- **RESERVE is point-in-time and reads $0 the moment the position is burned, even mid-rebuild.**
  Never equate `RESERVE = 0` with collapse — confirm with the Burn/Mint logs
  (`probe_migration.py`). The live-liquidity readout in that probe can be garbled
  (int24 tick decode); trust the **event logs**, which are reliable, over the snapshot.
- The script tracks one pool, one tick range, and fixed CEX/cluster address lists. A
  migration to a new range/pool, or flows to unlisted addresses, can hide the money —
  when reconciliation doesn't close, widen the search rather than trusting the defaults.
- This is monitoring, not financial or legal advice.
