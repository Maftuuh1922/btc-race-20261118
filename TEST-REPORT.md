# Test report — btc-race-24h-20261118-1444 dev window

Date: 2026-11-18 (WIB). Dev window: 1,440 one-minute cbBTC bars
($65,083.31 → $63,260.75, −2.80%). Start capital $1,000 USDC.

## Method

The kit's official `grade-local --driver process` cannot grade a Python bot
on this machine (its process sandbox runs Node 22 only; Python runs only
inside Docker, which is not installed here). The bot was therefore graded
with a protocol-level replay driver (`replay.py`, kept outside this repo)
that speaks `agent-fun/bars-replay/v1` to `python3 -P -s main.py` and
scores it with the harness's own integer fill model, reimplemented from
`contracts/bars-protocol.ts` in the kit: fill at the next bar's open, 4 bps
fee + 2 bps slippage + constant-product impact against `o_depth`,
max-slippage checked against the decision close, positions flattened at the
last close. The driver was cross-checked against the official scorer on the
kit baselines (see below).

## Result (chosen parameters)

| Metric | Value |
|---|---|
| Net PnL (dev) | **+$9.80** |
| Final equity | $1,009.80 |
| Return | +0.98% |
| Trades (filled orders) | 2 (1 round trip) |
| Max drawdown | 0.12% |
| Dev gate (PnL > $0) | **PASS** |
| Guardrails (≥1 trade, DD ≤ 25%) | **PASS** |
| Determinism (2 runs, action logs byte-identical) | **PASS** |
| Net PnL at 2× fee (8 bps) | +$8.99 |
| Net PnL at 2× fee + 2× slippage | +$8.30 |

## Trade log (dev window)

| # | Signal | Fill |
|---|---|---|
| 1 | BUY $1,000 — tier-A crash signal at bar 71: 20-min drop −2.03%, RSI 16.1, close $63,435.57 (+0.21% above trailing 5-bar low $63,365.56) | bar 72 open $63,514.05 → fill $63,617.14 (impact 12.9 bps), qty 0.015588 BTC |
| 2 | SELL all — take-profit at bar 80: position +1.01%, RSI 59.2, close $64,312.52 | bar 81 open $64,378.70 → fill $64,291.88, proceeds $1,009.80 |

Net: +$9.80 after all fees, slippage and impact.

The tier-B dip signal never fired in bars 0–1380 on this window. Two
tier-B signals did appear in the final hour (bars ~1437/1439, into the
closing selloff); both are blocked by the `NO_NEW_AFTER = 1380` rule — before
that rule existed they lost −$3.70 and −$1.11 (flattened at the last close).

## Parameters used

- Tier A: `DROP_THR = 0.012` (20-min drop), `RSI_ENTRY = 35`,
  `BOUNCE_THR = 0.001` (vs trailing 5-bar low), `TP_A = 0.010`,
  `SL_A = 0.004`, `TIMEOUT_A = 30`, size = all cash.
- Tier B: `DIP_B = 0.0025` (below SMA(20)), `RSI_B = 35`, same bounce,
  `TP_B = 0.004`, `SL_B = 0.0035`, `TIMEOUT_B = 30`, size = half capital.
- `RSI_EXIT = 65`, `MAX_SLIPPAGE_BPS = 100`, `NO_NEW_AFTER = 1380`,
  RSI(14) Wilder's, SMA(20).

## Robustness — parameter variations (exact replay, same driver)

The dev result is one round trip, so the variations below mostly move the
same trade; they are reported to show the choice is a plateau, not a
knife-edge fit.

| Variation | Net PnL | Trades | Max DD |
|---|---|---|---|
| Chosen (TP_A 1.0%) | **+$9.80** | 2 | 0.12% |
| TP_A 0.8% (exits one bar earlier) | +$7.12 | 2 | 0.16% |
| TP_A 1.2% (never hits; timeout exit) | +$3.50 | 2 | 0.82% |
| DROP_THR 1.0% / 1.5% | +$9.80 | 2 | 0.12% |
| SL_A 0.6% | +$9.80 | 2 | 0.12% |
| DIP_B 0.30% / RSI_B 30 / SL_B 0.30% | +$9.80 | 2 | 0.12% |
| Tier B disabled (crash-only) | +$9.80 | 2 | 0.12% |
| NO_NEW_AFTER 1410 (instead of 1380) | +$9.80 | 2 | 0.12% |

TP_A in 0.9–1.05% all give +$9.80 (same exit bar). Every variation stays
positive; the worst tested is +$3.50.

## Baselines (official `grade-local --driver process`, same dev window)

| Bot | Net PnL | Trades | Max DD |
|---|---|---|---|
| rsi-bollinger | −$39.92 | 19 | 4.35% |
| ema-cross | −$148.17 | 80 | 14.97% |
| momentum | −$23.87 | 1 | 3.24% |
| adx-momentum | −$75.57 | 30 | 7.56% |
| buy-and-hold | −$31.63 | 1 | 3.25% |
| hold-cash | $0.00 | 0 | 0.00% |
| **this bot** | **+$9.80** | **2** | **0.12%** |

All six baselines fail the dev gate; this bot is the only one tested that
passes it.

## Honest limitations

- The dev profit comes from a single trade on the window's one big
  capitulation bounce (bars 65–71, −2.6% then +1.6% in 15–60 min). The
  strategy is deliberately selective; on a quiet race window it may trade
  only 0–3 times. Tier B exists to keep it active in that case, but its
  edge on the dev window is unproven (0 qualifying trades in 1,380 bars).
- The race window is unseen prices. A +$9.80 dev score says nothing about
  the race score except that the bot passed the gate and its rules are
  deterministic and cost-aware.
- The $10 target was missed by $0.20: the bounce's extractable profit with
  causal timing is ~+$9.80 (perfect-timing upper bound ≈ +$13.60). No
  parameter was pushed past the plateau to chase the round number.
