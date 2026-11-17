#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/hatch/workspace/makefun/btc-race-24h-20261117-0603')
from backtest import *

results = []

def score(name, decide):
    full = run(decide)
    h1 = run(decide, lo=0, hi=720)
    h2 = run(decide, lo=720, hi=1440)
    results.append((full['pnl'], name, full['trades'], full['maxdd'], h1['pnl'], h2['pnl']))
    return full

# --- 1. EMA cross with TP/SL/trailing ---
for fast in (30, 60, 120):
    for slow in (180, 240, 360):
        if fast >= slow:
            continue
        ef, es = ema(C, fast), ema(C, slow)
        for tp in (0.02, 0.03):
            for sl in (0.015, 0.025):
                def make_decide(ef=ef, es=es, tp=tp, sl=sl):
                    def decide(i, st):
                        if i < slow:
                            return []
                        if st['qty'] > 0:
                            px = C[i]
                            if px >= st['entry'] * (1 + tp) or px <= st['entry'] * (1 - sl):
                                return [('sell', st['qty'])]
                            if ef[i] < es[i]:
                                return [('sell', st['qty'])]
                            return []
                        if ef[i] > es[i] and ef[i-1] <= es[i-1]:
                            return [('buy', st['cash'])]
                        return []
                    return decide
                score(f'ema{fast}/{slow} tp{tp} sl{sl}', make_decide())

# --- 2. Dip-buy (mean reversion vs rolling high) ---
for wn in (120, 240, 480):
    rmax = rolling_max(H, wn)
    for dip in (0.008, 0.012, 0.016, 0.02):
        for tp in (0.008, 0.012, 0.02):
            for sl in (0.01, 0.015):
                def make_decide(rmax=rmax, dip=dip, tp=tp, sl=sl):
                    def decide(i, st):
                        if i < wn:
                            return []
                        if st['qty'] > 0:
                            px = C[i]
                            if px >= st['entry'] * (1 + tp) or px <= st['entry'] * (1 - sl):
                                return [('sell', st['qty'])]
                            return []
                        if C[i] <= rmax[i] * (1 - dip):
                            return [('buy', st['cash'])]
                        return []
                    return decide
                score(f'dip wn{wn} dip{dip} tp{tp} sl{sl}', make_decide())

# --- 3. Bollinger mean reversion ---
for wn in (60, 120):
    sm = sma(C, wn)
    for sig in (2.0, 2.5):
        for tp in (0.01, 0.02):
            for sl in (0.015, 0.025):
                def make_decide(sm=sm, wn=wn, sig=sig, tp=tp, sl=sl):
                    def decide(i, st):
                        if i < wn:
                            return []
                        w = C[i-wn+1:i+1]
                        m = sum(w)/wn
                        sd = (sum((x-m)**2 for x in w)/wn) ** 0.5
                        lo_band = m - sig*sd
                        if st['qty'] > 0:
                            px = C[i]
                            if px >= m or px >= st['entry']*(1+tp) or px <= st['entry']*(1-sl):
                                return [('sell', st['qty'])]
                            return []
                        if C[i] < lo_band:
                            return [('buy', st['cash'])]
                        return []
                    return decide
                score(f'bb wn{wn} sig{sig} tp{tp} sl{sl}', make_decide())

# --- 4. Breakout ---
for wn in (60, 120, 240):
    rmax = rolling_max(H, wn)
    rmin = rolling_min(L, wn)
    for tp in (0.015, 0.025):
        for sl in (0.01, 0.015):
            def make_decide(rmax=rmax, tp=tp, sl=sl):
                def decide(i, st):
                    if i < wn:
                        return []
                    if st['qty'] > 0:
                        px = C[i]
                        if px >= st['entry']*(1+tp) or px <= st['entry']*(1-sl):
                            return [('sell', st['qty'])]
                        return []
                    if C[i] > rmax[i-1]:
                        return [('buy', st['cash'])]
                    return []
                return decide
            score(f'break wn{wn} tp{tp} sl{sl}', make_decide())

results.sort(reverse=True)
print(f"{'pnl':>8} {'trades':>6} {'maxdd%':>7} {'h1':>8} {'h2':>8}  name")
for pnl, name, tr, dd, h1, h2 in results[:25]:
    print(f"{pnl:8.2f} {tr:6d} {dd*100:7.2f} {h1:8.2f} {h2:8.2f}  {name}")
print('...')
print('total candidates:', len(results))
