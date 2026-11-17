// Dip-buyer for the BTC 24h race (agent-fun/bars-replay/v1, long only, one asset: CBBTC).
//
// Idea: on 1-minute bars BTC mostly chops inside a ~2% band while drifting slowly, and
// a full round trip costs ~26 bps (4 bps fee + 2 bps slippage + ~7-13 bps of pool impact
// each way), so fast signals (1-minute EMA crosses) bleed to death on fees. This bot
// trades rarely and only on a real dip: it buys all its cash when the close falls at
// least 1.2% below the highest high of the last 480 bars (8 hours), then sells the
// whole position at +0.8% over its entry fill or at -1.5% under it, whichever comes
// first. On the published dev window (1,440 bars) that is 5 trades, max drawdown
// ~1.5%, net PnL about +$14 on $1,000 — positive on both halves of the window
// (+$4.3 / +$5.8) — while the kit's ema-cross baseline loses -$106, rsi-bollinger
// -$24 and buy-and-hold makes only +$1.07 on the same window.
//
// Everything is integer math on the bar values (no floats, no clock, no randomness),
// so two runs on the same data produce the same orders byte for byte.

import { runBars, type BarsState, type BuyInput, type SellInput } from './vendor/makefun-bars.ts';

const SYMBOL = 'CBBTC';
/** Rolling window for the dip reference: the highest high of the last 480 bars. */
const WINDOW_BARS = 480;
/** Buy when the close is at least this far below that high, in basis points. */
const DIP_BPS = 120;
/** Sell at this gain over the entry fill, in basis points. */
const TAKE_PROFIT_BPS = 80;
/** Sell at this loss under the entry fill, in basis points. */
const STOP_LOSS_BPS = 150;
/** Never pay more than 1% past the close the order was decided on. */
const MAX_SLIPPAGE_BPS = 100;

const highs: bigint[] = [];
let entryPrice: bigint | null = null;

function rollingHigh(): bigint | null {
  if (highs.length < WINDOW_BARS) return null;
  let m = highs[0]!;
  for (const h of highs) if (h > m) m = h;
  return m;
}

/** Sell the whole position in one order, capped at MAX_SLIPPAGE_BPS of slippage. */
function sellAll(qty: bigint): SellInput[] {
  return [{ side: 'sell', symbol: SYMBOL, qty, max_slippage_bps: MAX_SLIPPAGE_BPS }];
}

await runBars({
  onBatch(state: BarsState, batch) {
    // Learn the entry fill price from the fills this batch reports, so the take-profit
    // and stop-loss are measured against what the buy actually paid, fees included.
    for (const f of batch.fills) {
      if (f.status !== 'filled' || f.symbol !== SYMBOL) continue;
      if (f.side === 'buy') entryPrice = BigInt(f.price);
      if (f.side === 'sell') entryPrice = null;
    }

    const bar = batch.bars.find((b) => b.symbol === SYMBOL);
    if (bar === undefined || state.warmingUp) return [];
    highs.push(BigInt(bar.h));
    if (highs.length > WINDOW_BARS) highs.shift();

    const close = BigInt(bar.c);
    const held = state.positions.get(SYMBOL);

    if (held !== undefined && held.qty > 0n) {
      // Exit: take profit, stop loss, or fall back to the cost basis if the fill price
      // was never seen (it always is, one batch after the buy fills).
      if (entryPrice !== null) {
        if (close * 10_000n >= entryPrice * (10_000n + BigInt(TAKE_PROFIT_BPS))) {
          return sellAll(held.qty);
        }
        if (close * 10_000n <= entryPrice * (10_000n - BigInt(STOP_LOSS_BPS))) {
          return sellAll(held.qty);
        }
      } else {
        const value = state.value(SYMBOL, held.qty);
        if (value * 10_000n >= held.cost * (10_000n + BigInt(TAKE_PROFIT_BPS))) {
          return sellAll(held.qty);
        }
        if (value * 10_000n <= held.cost * (10_000n - BigInt(STOP_LOSS_BPS))) {
          return sellAll(held.qty);
        }
      }
      return [];
    }

    // Entry: a dip of at least DIP_BPS below the 480-bar high, with a full window of
    // history behind it. All cash, one order: splitting it would only pay the same
    // impact twice.
    const high = rollingHigh();
    if (high === null) return [];
    if (close * 10_000n <= high * (10_000n - BigInt(DIP_BPS))) {
      const cash = state.cash;
      if (cash < BigInt(state.hello.fees.min_notional_quote_units)) return [];
      return [{ side: 'buy', symbol: SYMBOL, notional_quote_units: cash, max_slippage_bps: MAX_SLIPPAGE_BPS } satisfies BuyInput];
    }
    return [];
  },
});
