# Neyro/Aurum daily health-check guide

## What you're monitoring
`watch_simple.py` is a read-only, on-chain (BSC) scanner for the Neyro / Aurum
"Neyro AI" yield platform. Prior forensic work concluded the platform is
**structurally a Ponzi**: there is no on-chain evidence of real trading yield, user
payouts are funded by new user deposits, and surplus is swept one-way to Binance.

This is **not** an "is it healthy?" check in the investment sense. Each day you are
checking three things:
1. **Still behaving like a Ponzi?** (primary test: deposit/mint coverage ~100%; running return/extracted ratio near zero)
2. **Signs of imminent collapse?** (reserve draining, deposits falling, sweep suppression)
3. **Any anomaly that challenges the Ponzi conclusion?** (external capital minting into position, or funds returning from Binance at meaningful scale) — flag these loudly.

---

## Primary Ponzi test: deposit/mint coverage

**This is the single most diagnostic ongoing signal.** Each window the script reports
`deposit/mint coverage: X%`:

- **~100%** — mints into the position are funded entirely by recycled user deposits.
  Pure pass-through. Structurally a Ponzi. This is the baseline.
- **>100% or <85%** — mints exceed deposits. Capital is entering from somewhere other
  than the deposit funnel. Could be a real trading operation returning profits, or an
  operator top-up from an external source.
  **This is the strongest possible "not a pure Ponzi" signal. FLAG immediately and trace the source.**

One-time anomalies in RETURN or EXTERNAL only matter if coverage also shifts. A $50k
return against $10M+ lifetime extraction at 100% coverage is operational noise.

---

## Running extraction balance (the real trading test)

`record_stats.py` accumulates two running lifetime totals in `daily_stats.csv`:

- **`cum_collects`**: all USDT ever swept OUT of the position (to Binance and other sinks).
- **`cum_return`**: all USDT ever confirmed flowing BACK from Binance into the cluster.

**The ratio `cum_return / cum_collects`** is the cleanest test of whether this is a
real trading operation:

| Ratio | Interpretation |
|---|---|
| ~0% | One-way extraction. Consistent with Ponzi. |
| Rising above ~5% | Meaningful capital returning. Watch for trend. |
| >10% and climbing | Investigate whether trading profits are actually cycling back. |
| >50% | Would strongly suggest a real treasury. Extraordinary signal. |

Report this ratio in every daily check. A single RETURN event only matters in context
of the ratio — flag the amount AND what percentage of lifetime extraction it represents.

---

## What the script prints each run (six blocks + a VERDICT line)

- `[MINT]   X USDT ... internal: A | EXTERNAL: B` — capital added to the position; EXTERNAL = not from the bot/funnel.
- `[DEPOSIT]  X USDT user deposits into funnel` + `deposit/mint coverage: X%`
- `[SWEEP]   X USDT left pool via platform collects, N recipients` (flags new/unknown sinks)
- `[RESERVE]  platform position holds X USDT now (pool tick T)` — the tank level; most important number for collapse risk.
- `[POSITION] window flow: mints IN - collects OUT = NET`
- `[RETURN]   Binance -> cluster: direct X + indirect Y USDT`
- `VERDICT:` script's one-line read.

---

## How to read each signal

| Signal | Ponzi-consistent (expected) | Would challenge Ponzi conclusion — FLAG |
|---|---|---|
| **Deposit/mint coverage** *(primary)* | **~100%** — position fed entirely by new user deposits. Core structural Ponzi signal. | **<85% or >100%** — mints exceed deposits; outside capital entering. **Strongest single flag. Trace source immediately.** |
| **Running ratio** `cum_return / cum_collects` | **Near 0%** — one-way extraction. | **Rising above 5%, especially if also >$100k** — report trend and ratio in every check. |
| **EXTERNAL mint** | `EXTERNAL: 0` | **`EXTERNAL > ~$1k`** — outside address minted real capital into the position. **FLAG + report the address.** |
| **RETURN** | `0` | **`RETURN > 0`** — flag it AND immediately state it as % of `cum_collects`. Small % at 100% coverage = noise. Large % or recurring = investigate. |
| **COLLECTS (sweep)** | ~$540k–$590k per window | **Drop >50% or spike >50% from baseline** — operator changed behavior. Flag as `BEHAVIORAL CHANGE`. Could signal monitoring evasion, pre-exit accumulation, or an operational shift. |
| **RESERVE** (tank) | Stable; historically ~$0.94M–$1.19M | Rising while coverage stays ~100% → operator suppressing sweeps (note, not necessarily a Ponzi challenge). Rising while coverage <100% → **external top-up; FLAG.** |
| **RESERVE — collapse risk** | — | **Falling steadily day over day** → compute `runway_days = reserve / avg_daily_decline` and FLAG. |
| **DEPOSIT** | ~$550k–$570k per window | **Sustained drop >30% vs recent days** → new money drying up; classic pre-collapse signal. **FLAG.** |
| **POSITION net** | Mildly negative/flat, replenished by deposits | Strongly negative repeatedly AND reserve falling → paying out faster than topping up. FLAG. |
| **SWEEP — unknown sink** | Collects to known Binance route | **New, large, unrecognized sink** that then forwards to a CEX → note address and watch. |

---

## Baseline reference numbers (per ~9h run)

- Reserve: **~$0.94M–$1.19M** (historical); rose anomalously to ~$4.33M on 2026-06-13 — under investigation.
- Deposits: **~$550k–$570k**.
- Deposit/mint coverage: **~100%** (all mints funded by recycled user deposits).
- Mints into position: **~$320k–$570k, 100% internal**.
- Collects out (sweeps): **~$540k–$590k** — watch for deviations.
- Position net: **~−$200k to −$230k** typical; judge drawdown by RESERVE trend, not single-window net.
- EXTERNAL: **historically $0**.
- RETURN: **$53,800 indirect seen 2026-06-13** (first nonzero); ratio ~2.5% of lifetime collects at time — not conclusive.
- Known benign sink `0x46c2abb69c9a91a86352e11b7ed4bce56a9998aa` (~$10k, parked user wallet) — do not alert unless it grows or forwards to a CEX.

---

## Day-over-day tracking (required — the script is stateless)

`record_stats.py` tracks these automatically in `daily_stats.csv`. Review each:

- **`reserve`** — multi-day downtrend → compute runway. Sudden jump → cross-check collects and coverage.
- **`deposits`** — sustained drop → new money slowing; pre-collapse signal.
- **`collects` / `collects_vs_baseline`** — deviation from ~$540k. Flag if >±50%.
- **`deposit_mint_coverage`** — must stay ~100%. Any departure is the highest-priority investigation.
- **`cum_collects` + `cum_return` + ratio** — report the running balance ratio in every check.

---

## Daily health-check output

Produce a short report with:

1. **Headline status**, one of:
   - `STABLE PONZI PASS-THROUGH` (coverage ~100%, reserve steady, deposits steady, collects normal, ratio ~0%)
   - `DRAINING — COLLAPSE RISK` (reserve trending down or deposits falling; include runway estimate)
   - `ANOMALY — EXTERNAL CAPITAL` (coverage <85% or EXTERNAL mint > 0)
   - `ANOMALY — RETURN FLOW` (RETURN > 0) — always include the ratio vs lifetime extraction
   - `BEHAVIORAL CHANGE` (collects deviate >50% from ~$540k baseline without other explanation)

2. **Key numbers**:
   - Reserve today vs prior (Δ)
   - Deposits today vs ~$550k baseline
   - **Deposit/mint coverage %**
   - Collects today vs ~$540k baseline (Δ%)
   - EXTERNAL mint, RETURN direct + indirect
   - **Running balance: `cum_collects` total, `cum_return` total, ratio %**

3. **Flags**: any row above that tripped, with relevant address/amount.

4. **One-line takeaway** in plain language.

---

## Caveats (state when relevant)

- On-chain only: cannot see CEX-internal activity, off-exchange OTC, or non-BSC chains.
  "No return on BSC/USDT" is not a categorical "nothing came back."
- One daily run samples ~9h of 24h. Good for RESERVE trend and structural signals.
- RESERVE math assumes pool tick < 45000; if `[RESERVE] unavailable` appears, note it rather than treating it as $0.
- `cum_return` captures only BSC/USDT confirmed Binance→cluster flows. Return via other
  chains, stablecoins, or OTC is invisible to this monitor.
- This is monitoring, not financial or legal advice.
