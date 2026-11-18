"""Dip-buy mean-reversion bot for make.fun btc-race-24h-20261118-1444.

Strategy (long only, $1,000 paper USDC, 1-minute cbBTC bars):
  The dev window falls 2.8% and every trend-following / slow mean-reversion
  baseline loses on it. The only durable edge in the data is the
  capitulation bounce: a sharp selloff that exhausts itself and snaps back.
  This bot therefore stays in cash by default and only buys after a selloff,
  with a bounce confirmation so it never catches a falling knife mid-plunge.

  Tier A (crash): the 20-minute drop from the trailing high is >= 1.2% AND
    RSI(14) <= 35 AND the close has recovered >= 0.1% above the trailing
    5-bar low. Buys with all remaining cash. Exit at +1.0% / -0.4% / 30 bars.
  Tier B (regular dip): the close is >= 0.25% below SMA(20) AND RSI(14)
    <= 35 AND the same bounce confirmation. Buys half the starting capital.
    Exit at +0.4% / -0.35% / 30 bars. If a crash signal fires while a tier-B
    position is held, the remaining cash is added and the position is
    promoted to tier A.
  Any held position also exits when RSI(14) >= 65.

  All arithmetic is float64 on the same operations every run, no clock, no
  randomness, no network, no files: the same bars give the same orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
MAX_SLIPPAGE_BPS = 100

# --- indicators ---
SMA_N = 20
RSI_N = 14
DROP_W = 20            # trailing window (bars) for the crash drop
BOUNCE_W = 5           # trailing window (bars) for the bounce low

# --- tier A: crash bounce ---
DROP_THR = 0.012       # 20-min drop from trailing high
RSI_ENTRY = 35
BOUNCE_THR = 0.001     # close >= trailing low * (1 + this)
TP_A = 0.010
SL_A = 0.004
TIMEOUT_A = 30

# --- tier B: regular dip ---
DIP_B = 0.0025         # close below SMA(20) by this much
RSI_B = 35
TP_B = 0.004
SL_B = 0.0035
TIMEOUT_B = 30

RSI_EXIT = 65

# Do not open a NEW position after this batch seq. Both windows are 1,440
# bars and any position still held at the end is flattened at the last close,
# so an entry opened in the final hour rarely has time to reach its target
# and mostly just realises the flatten loss. (Upgrading an already-held
# position on a crash signal is still allowed.)
NO_NEW_AFTER = 1380


class Series:
    """Per-symbol indicator state, updated from each bar's close."""

    def __init__(self):
        self.closes = []          # float closes in USDC
        self.rsi_gain = None      # Wilder averages, None until seeded
        self.rsi_loss = None
        self._first = []          # first RSI_N changes while seeding

    def push(self, close):
        if self.closes:
            ch = close - self.closes[-1]
            if self.rsi_gain is None:
                self._first.append(ch)
                if len(self._first) == RSI_N:
                    self.rsi_gain = sum(x for x in self._first if x > 0) / RSI_N
                    self.rsi_loss = sum(-x for x in self._first if x < 0) / RSI_N
            else:
                up = ch if ch > 0 else 0.0
                dn = -ch if ch < 0 else 0.0
                self.rsi_gain = (self.rsi_gain * (RSI_N - 1) + up) / RSI_N
                self.rsi_loss = (self.rsi_loss * (RSI_N - 1) + dn) / RSI_N
        self.closes.append(close)

    def rsi(self):
        if self.rsi_gain is None:
            return None
        moved = self.rsi_gain + self.rsi_loss
        return 50.0 if moved == 0 else 100.0 * self.rsi_gain / moved

    def sma(self, n):
        if len(self.closes) < n:
            return None
        return sum(self.closes[-n:]) / n

    def trail_max(self, n):
        if len(self.closes) < n:
            return None
        return max(self.closes[-n:])

    def trail_low(self, n):
        if len(self.closes) < n + 1:
            return None
        return min(self.closes[-n - 1:])


SERIES = {}
TIER = 0          # 0 = flat, 1 = tier-B dip, 2 = tier-A crash
ENTRY_BAR = -1
HALF_CAPITAL = None


def _price_scale(state):
    return state.hello["symbols"][0]["price_scale"]


def on_batch(state, batch):
    global TIER, ENTRY_BAR, HALF_CAPITAL
    if HALF_CAPITAL is None:
        HALF_CAPITAL = int(state.hello["capital"]["quote_units"]) // 2

    if state.warming_up:
        return []

    scale = 10 ** _price_scale(state)
    fresh = False
    for bar in batch["bars"]:
        if bar["symbol"] != SYMBOL:
            continue
        s = SERIES.get(SYMBOL)
        if s is None:
            s = SERIES[SYMBOL] = Series()
        s.push(int(bar["c"]) / scale)
        fresh = True
    if not fresh:
        return []

    s = SERIES[SYMBOL]
    rsi = s.rsi()
    sma20 = s.sma(SMA_N)
    if rsi is None or sma20 is None:
        return []

    close = s.closes[-1]
    dip = (sma20 - close) / sma20
    tmax = s.trail_max(DROP_W)
    drop = (tmax - close) / tmax if tmax is not None else None
    tlow = s.trail_low(BOUNCE_W)
    bounced = tlow is not None and close >= tlow * (1.0 + BOUNCE_THR)

    held = state.positions.get(SYMBOL)
    orders = []

    if held is None:
        tier = 0
        if state.seq < NO_NEW_AFTER:
            if drop is not None and drop >= DROP_THR and rsi <= RSI_ENTRY and bounced:
                tier = 2
            elif dip >= DIP_B and rsi <= RSI_B and bounced:
                tier = 1
        if tier:
            amount = state.cash if tier == 2 else min(state.cash, HALF_CAPITAL)
            if amount >= int(state.hello["fees"]["min_notional_quote_units"]):
                orders.append({"side": "buy", "symbol": SYMBOL,
                               "notional_quote_units": amount,
                               "max_slippage_bps": MAX_SLIPPAGE_BPS})
                TIER = tier
                ENTRY_BAR = state.seq
        return orders

    # holding a position: check upgrade, then exits
    value = state.value(SYMBOL, held.qty)
    cost = held.cost
    gain = (value - cost) / cost if cost > 0 else 0.0
    held_bars = state.seq - ENTRY_BAR

    if TIER == 1 and drop is not None and drop >= DROP_THR and bounced and state.cash > 0:
        orders.append({"side": "buy", "symbol": SYMBOL,
                       "notional_quote_units": state.cash,
                       "max_slippage_bps": MAX_SLIPPAGE_BPS})
        TIER = 2
        return orders

    if TIER == 2:
        tp, sl, timeout = TP_A, SL_A, TIMEOUT_A
    else:
        tp, sl, timeout = TP_B, SL_B, TIMEOUT_B

    if gain >= tp or gain <= -sl or rsi >= RSI_EXIT or held_bars >= timeout:
        orders.append({"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                       "max_slippage_bps": MAX_SLIPPAGE_BPS})
        TIER = 0
    return orders


makefun_bars.run(on_batch)
