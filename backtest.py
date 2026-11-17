#!/usr/bin/env python3
"""Offline backtester replicating bars-replay/v1 fills (approx, float math).
Fees: 4bps on fill notional; slippage 2bps; impact 1+a/D vs o_depth of fill bar.
Orders decided on bar k fill at bar k+1 open. Final flatten at last close.
"""
import gzip, json, math, sys

K = '/home/hatch/workspace/makefun/btc-race-24h-20261117-0603-kit/btc-race-24h-20261117-0603-kit'
bars = [json.loads(l) for l in gzip.open(f'{K}/dataset/bars/CBBTC.ndjson.gz', 'rt')]
O = [float(b['o']) / 1e5 for b in bars]
H = [float(b['h']) / 1e5 for b in bars]
L = [float(b['l']) / 1e5 for b in bars]
C = [float(b['c']) / 1e5 for b in bars]
D = [float(b['o_depth'][0]) / 1e6 for b in bars]  # USDC depth at open
DC = [float(b['c_depth'][0]) / 1e6 for b in bars]
N = len(C)

FEE = 0.0004
SLIP = 0.0002

def run(decide, start_cash=1000.0, lo=0, hi=None):
    """decide(i, state) -> list of ('buy', notional_usd) or ('sell', qty_btc) decided on bar i.
    Fills at bar i+1 open. Returns dict with pnl, trades, maxdd."""
    if hi is None:
        hi = N
    cash = start_cash
    qty = 0.0
    cost = 0.0  # cost basis of position in USD (incl fees)
    entry_price = 0.0
    peak = start_cash
    mdd = 0.0
    trades = 0
    equity_hist = []
    pending = []  # orders decided, to fill at next open
    for i in range(lo, hi):
        # fill pending orders at bar i open (skip i==0, nothing pending)
        if pending and i > 0:
            op = O[i]; depth = D[i]
            for kind, amt in pending:
                if kind == 'buy':
                    spend = min(amt, cash)
                    if spend < 1.0:
                        continue
                    fee = FEE * spend
                    a = spend - fee
                    m = 1 + a / depth
                    fill = op * (1 + SLIP) * m
                    q = a / fill
                    cash -= spend
                    qty += q
                    cost += spend
                    entry_price = fill
                    trades += 1
                else:  # sell qty amt (btc)
                    q = min(amt, qty)
                    if q <= 0:
                        continue
                    gross = q * op
                    if gross < 1.0 and q < qty:
                        continue
                    m = 1 + gross / depth
                    fill = op * (1 - SLIP) / m
                    proceeds = q * fill
                    fee = FEE * proceeds
                    cash += proceeds - fee
                    qty -= q
                    if qty < 1e-12:
                        cost = 0.0
                    else:
                        cost *= (1 - q / (q + qty)) if False else 1  # approx: keep cost simple
                    trades += 1
            pending = []
        # equity at close
        eq = cash + qty * C[i]
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
        equity_hist.append(eq)
        if i == hi - 1:
            break
        orders = decide(i, dict(cash=cash, qty=qty, cost=cost, entry=entry_price, eq=eq))
        pending = orders or []
    # final flatten at last close of the range
    if qty > 0:
        op = C[hi - 1]; depth = DC[hi - 1]
        gross = qty * op
        m = 1 + gross / depth
        fill = op * (1 - SLIP) / m
        proceeds = qty * fill
        cash += proceeds - FEE * proceeds
        qty = 0.0
    pnl = cash - start_cash
    return dict(pnl=pnl, trades=trades, maxdd=mdd, final=cash)

def ema(series, n):
    k = 2 / (n + 1)
    out = []
    e = None
    for x in series:
        e = x if e is None else x * k + e * (1 - k)
        out.append(e)
    return out

def sma(series, n):
    out = []
    s = 0.0
    for i, x in enumerate(series):
        s += x
        if i >= n:
            s -= series[i - n]
        out.append(s / min(i + 1, n))
    return out

def rolling_max(series, n):
    out = []
    for i in range(len(series)):
        out.append(max(series[max(0, i - n + 1):i + 1]))
    return out

def rolling_min(series, n):
    out = []
    for i in range(len(series)):
        out.append(min(series[max(0, i - n + 1):i + 1]))
    return out

def rsi_wilder(changes, n=14):
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    out = [None] * len(changes)
    if len(changes) < n:
        return out
    g = sum(gains[:n]) / n
    l = sum(losses[:n]) / n
    out[n - 1] = 50.0 if g + l == 0 else 100 * g / (g + l)
    for i in range(n, len(changes)):
        g = (g * (n - 1) + gains[i]) / n
        l = (l * (n - 1) + losses[i]) / n
        out[i] = 50.0 if g + l == 0 else 100 * g / (g + l)
    return out
