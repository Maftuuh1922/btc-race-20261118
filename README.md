# cbBTC Dip-Buy Mean-Reversion Bot — make.fun btc-race-24h-20261118-1444

Paper-money trading bot (no real money) for the "Race a BTC trading bot live
for 24 hours" competition. Trades Coinbase Wrapped BTC (cbBTC) against USDC
on 1-minute on-chain bars from an Orca Whirlpool, starting with $1,000.

## Strategy

The dev window falls 2.8% ($65,083 → $63,261) and every kit baseline loses
on it (RSI-Bollinger −$39.92, EMA-cross −$148.17, momentum −$23.87,
ADX-momentum −$75.57, buy-and-hold −$31.63). The only durable edge in the
data is the **capitulation bounce**: a sharp selloff that exhausts itself
and snaps back. This bot therefore stays in cash by default and only buys
after a selloff, with a bounce confirmation so it never catches a falling
knife mid-plunge.

**Tier A — crash bounce (the money trade).** Enter when all three hold:
- the 20-minute drop from the trailing high is ≥ 1.2%, and
- RSI(14) ≤ 35, and
- the close has recovered ≥ 0.1% above the trailing 5-bar low.

Buys with all remaining cash. Exits at +1.0% take-profit, −0.4% stop-loss,
or after 30 bars, whichever comes first.

**Tier B — regular dip (insurance).** Enter when the close is ≥ 0.25%
below SMA(20), RSI(14) ≤ 35, and the same bounce confirmation holds.
Buys half the starting capital. Exits at +0.4% / −0.35% / 30 bars.
If a crash signal fires while a tier-B position is held, the remaining cash
is added and the position is promoted to tier A. Tier B exists so the bot
still trades (and can still profit) in a race window with no crash; on the
dev window it never fires in the first 1,380 bars.

**Other rules.**
- Any held position also exits when RSI(14) ≥ 65.
- No NEW position is opened after batch 1380. Both windows are 1,440 bars
  and anything still held at the end is flattened at the last close, so a
  late entry rarely has time to reach its target and mostly just realises
  the flatten loss. (Upgrading an already-held position is still allowed.)
- Max slippage 100 bps per order; at most one order per reply; long only.

## Files

- `main.py` — the bot (Python 3.13, standard library only).
- `vendor/makefun_bars.py` — byte-identical copy of the kit's Python SDK
  shim (`sdk/makefun_bars.py`), as the rules allow.
- `README.md` — this file. `LICENSE` — MIT. `TEST-REPORT.md` — dev results.

## How it runs

The grader runs `python3 -P -s /bot/main.py` with `PYTHONHASHSEED=0`.
The bot speaks `agent-fun/bars-replay/v1` on stdin/stdout through the SDK
shim: one reply per batch, echoing its seq. All arithmetic is float64 on
the same operations every run — no clock, no randomness, no network, no
files outside the repository — so the same bars give the same orders.
