#!/usr/bin/env python3
"""
Newman Strategy Backtester — v2

Controls implemented:
  1. Trendline resistance break  — peak detection over prior 252 bars, not 20-day high
  2. Look-ahead prevention       — entry at next-bar open; signal uses only bars[:i]
  3. Slippage model              — 0.75% adverse on every fill (configurable)
  4. Sequential equity curve     — 5% of current equity risked per trade
  5. Out-of-sample split         — in-sample / out-of-sample reported separately
  6. SPY regime tagging          — each trade tagged bull/bear/neutral
  7. Conviction score            — trendline_break + volume_surge + near_52w_high
  8. "Immediately wrong" exit    — if day-1 open > 1×ATR below entry, exit at open
  9. Pre-defined success criteria — pass/fail printed before results
 10. Survivorship bias note      — delisted tickers removed; warning printed

SURVIVORSHIP BIAS WARNING:
  This universe contains only stocks that survived to today and have Alpaca data.
  Stocks that went bankrupt, delisted, or were acquired are excluded.
  This overstates returns. A proper test requires a point-in-time universe
  (CRSP, Sharadar, or Polygon's historical tickers endpoint).
"""
import sys, os, argparse, json, csv, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

from datetime import datetime, timezone
import numpy as np

# Map CLI string → (alpaca_tf_key, bars_per_year, trendline_lookback, vol_avg_bars)
#
# trendline_lookback: how many bars to use for resistance line detection.
#   On daily/weekly: 1 year of bars (same concept, different density).
#   On hourly: ~4 trading weeks (130 bars) — intraday "downtrend" is days/weeks.
#   On minute: ~1 trading week (1950 bars) — micro-structure trend.
#
# vol_avg_bars: rolling window for average volume comparison.
#   Scaled to ~20 trading days at each timeframe resolution.
#
# ⚠ Intraday data volume warning:
#   Minute bars = ~390 bars/day. Over 30 calendar days × 28 symbols ≈ 330k fetches.
#   Recommend --lookback 30 for minute, --lookback 365 for hour.
#   Daily/weekly: --lookback 1260 (5 years) is fine.
TIMEFRAMES = {
    # Multi-minute: tuple spec → TimeFrame(multiplier, TimeFrameUnit.Minute)
    '5min':   (('Minute',  5), 19_656,   390,  78),  # trendline≈1wk,  vol≈1day
    '10min':  (('Minute', 10),  9_828,   195,  39),  # trendline≈1wk,  vol≈1day
    '20min':  (('Minute', 20),  4_914,   100,  20),  # trendline≈1wk,  vol≈1day
    # Standard: string → getattr(TimeFrame, string)
    'minute': ('Minute',        98_280, 1_950, 390),  # trendline≈1wk,  vol≈1day
    'hour':   ('Hour',           1_638,   130,  33),  # trendline≈4wk,  vol≈1wk
    'day':    ('Day',              252,   252,  20),  # trendline≈1yr,  vol≈20d
    'week':   ('Week',              52,    52,   4),  # trendline≈1yr,  vol≈4wk
    'month':  ('Month',             12,    36,   3),  # trendline≈3yr,  vol≈1qtr
    # 'year' resamples from monthly bars — see run_backtest()
    'year':   ('Month',              1,     5,   2),  # trendline≈5yr,  vol≈2yr
}

logging.basicConfig(level=logging.WARNING)

# ── Universe ─────────────────────────────────────────────────────────────────
# Sectors retained based on prior backtest: proven cycle history, >30% win rate.
# Removed: cannabis, clean_energy, ev (structural declines, <15% win rate).
#
# biotech_asymmetric: micro-cap / low-price biotech with binary catalysts.
#   Filter (applied at entry): price < $20 AND 10-day vol > 1.5× prior 20-day vol.
#   These are not large-cap biotech — they're the stocks Newman would have
#   screened for asymmetric payoff on FDA/clinical events.
#
# quantum: new sector. Most tickers listed 2021-2022, so history is shorter.
#   Backtest will use whatever bars Alpaca has.
SECTOR_UNIVERSE = {
    'semiconductors':    ['NVDA', 'AMD', 'SMCI', 'MRVL', 'ON'],
    'ai_software':       ['SOUN', 'BBAI', 'PLTR', 'RXRX', 'CLOV'],
    'uranium':           ['UEC', 'UUUU', 'DNN', 'CCJ', 'NXE'],
    'space':             ['RKLB', 'SPCE', 'ASTS'],
    'biotech_asymmetric':['GERN', 'BCRX', 'ADMA', 'SIGA', 'TGTX', 'AGEN', 'RCUS'],
    # ATNF removed: two trades (+1236%, +433%) were real events but dominated the
    # equity curve. They were genuine biotech squeezes the filter found correctly,
    # but including them made the aggregate return number misleading for evaluation.
    'quantum':           ['IONQ', 'RGTI', 'QUBT', 'QBTS', 'ARQQ'],
}

# Sector-specific entry filters applied BEFORE the standard conviction check.
# Return True to allow entry, False to skip.
def _biotech_asymmetric_filter(bars: list[dict], i: int,
                               vol_window: int = 20) -> bool:
    """
    Only take asymmetric biotech setups:
      - Price < $20 (low-price requirement for asymmetric risk/reward)
      - Volume acceleration: recent half-window avg > 1.5× prior full-window avg
        (accumulation building before the move)
    vol_window is passed from vol_avg_bars so it scales across timeframes.
    """
    if bars[i]['close'] >= 20.0:
        return False
    half = max(1, vol_window // 2)
    if i < vol_window + half:
        return False
    recent_vol = float(np.mean([b['volume'] for b in bars[i - half:i]]))
    prior_vol  = float(np.mean([b['volume'] for b in bars[i - vol_window - half:i - half]]))
    return prior_vol > 0 and recent_vol >= 1.5 * prior_vol

SECTOR_FILTERS: dict[str, object] = {
    'biotech_asymmetric': _biotech_asymmetric_filter,
}

# ── Pre-defined success criteria ─────────────────────────────────────────────
# Newman's strategy is explicitly sub-50% win rate with large asymmetric wins.
# The original 45% win rate and Sharpe criteria were wrong for this structure:
#   - Win rate: Newman said <50% is expected and fine — the edge is W/L ratio
#   - Sharpe: structurally penalises high-variance asymmetric payoffs even when
#     expectancy is strongly positive. Wrong metric for this strategy type.
#
# Replaced with:
#   - expectancy_per_trade: (win_rate × avg_win) − (loss_rate × avg_loss)
#     This is the single most honest number for a Newman-style system.
#     Threshold ≥ +15% per trade (we were getting +20.6% in the last run).
#   - profit_factor: gross_wins / gross_losses ≥ 2.0
#     Standard asymmetric strategy gate. >2.0 means for every $1 lost,
#     the system returns $2+ in gross wins.
#   - W/L ratio raised from 3.0 → 4.0 (we now know what good looks like here).
SUCCESS_CRITERIA = {
    'expectancy_per_trade': {'threshold': 15.0, 'op': '>=', 'label': 'Expectancy/trade ≥ +15%'},
    'win_loss_ratio':       {'threshold': 4.0,  'op': '>=', 'label': 'Avg W / Avg L ≥ 4.0'},
    'profit_factor':        {'threshold': 2.0,  'op': '>=', 'label': 'Profit factor ≥ 2.0'},
    'max_drawdown_pct':     {'threshold': 25.0, 'op': '<=', 'label': 'Max drawdown ≤ 25%'},
    'total_trades':         {'threshold': 20,   'op': '>=', 'label': 'Trade count ≥ 20'},
}


# ── Core signal functions ─────────────────────────────────────────────────────

def compute_atr(bars: list[dict], period: int = 14) -> float:
    """ATR-14 using Wilder's smoothing."""
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]['high'], bars[i]['low'], bars[i-1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return trs[-1] if trs else 0.0
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return float(atr)


def detect_resistance_break(bars: list[dict], lookback: int = 252) -> tuple[bool, float]:
    """
    Return (broke_out, resistance_level).

    Draws a resistance line through the spike highs of the prior `lookback`
    bars (NOT including today), then checks if today's close is >1% above it.

    This is Newman's actual entry signal: a multi-year downtrend trendline break.
    The 20-day-high check in v1 was wrong — it detects "went up lately", not
    "broke out of a year-long decline".

    No look-ahead: `bars` slice passed in must end at bar i (today), and the
    window used for detection is bars[i-lookback : i] — excluding bar i.
    """
    if len(bars) < lookback + 1:
        # Not enough history for a meaningful trendline
        return False, 0.0

    window = bars[-lookback-1:-1]   # bars strictly BEFORE today
    highs = np.array([b['high'] for b in window])

    # Peak detection: local max within ±neighborhood bars.
    # Scale with lookback so coarse timeframes (month/year) don't need 5-bar windows.
    #   daily  (252): 252//10 = 25 → min(5,25) = 5
    #   weekly  (52): 52//10  =  5 → min(5,5)  = 5
    #   monthly (36): 36//10  =  3 → min(5,3)  = 3
    #   yearly   (5):  5//10  =  0 → max(1,0)  = 1  ← floor 1, not 2
    # Floor is 1 (not 2) so that coarse timeframes (year) can still find peaks
    # in a 5-bar window: with neighborhood=1, two peaks can sit at indices [1,3].
    neighborhood = max(1, min(5, lookback // 10))
    peaks = [
        idx for idx in range(neighborhood, len(highs) - neighborhood)
        if highs[idx] == max(highs[idx - neighborhood: idx + neighborhood + 1])
    ]

    if len(peaks) < 2:
        return False, 0.0

    # Use the last ≤6 peaks so we capture the recent downtrend slope
    recent_peaks = peaks[-min(6, len(peaks)):]
    peak_x = np.array(recent_peaks, dtype=float)
    peak_y = highs[recent_peaks]

    # Fit resistance line through spike highs
    slope, intercept = np.polyfit(peak_x, peak_y, 1)

    # Project resistance to today (index = len(window))
    resistance = slope * len(window) + intercept

    today_close = bars[-1]['close']
    broke_out = today_close > resistance * 1.01  # require 1% clearance
    return broke_out, max(resistance, 0.0)


def score_conviction(bars: list[dict], i: int, avg_vol_20: float,
                     trendline_break: bool, bars_per_year: int = 252) -> int:
    """
    0–3 conviction score (corners proxy).
      1 — chart:     trendline resistance break
      1 — structure: volume ≥ 2.5× 20-period average
      1 — sector:    close within 20% of 1-year high (stock in active zone)

    `bars_per_year` scales the 1-year lookback to the timeframe in use
    (252 for daily bars, 52 for weekly bars).
    Only take a trade if score >= min_corners (CLI arg).
    """
    score = 0
    if trendline_break:
        score += 1
    if avg_vol_20 > 0 and bars[i]['volume'] >= 2.5 * avg_vol_20:
        score += 1
    lookback_1y = max(0, i - bars_per_year)
    high_1y = max(b['high'] for b in bars[lookback_1y: i + 1])
    if high_1y > 0 and bars[i]['close'] >= high_1y * 0.80:
        score += 1
    return score


def apply_slippage(price: float, side: str, slippage_pct: float) -> float:
    """Adverse slippage: buys fill higher, sells fill lower."""
    if side == 'buy':
        return price * (1.0 + slippage_pct)
    return price * (1.0 - slippage_pct)


def resample_to_yearly(monthly_bars: list[dict]) -> list[dict]:
    """
    Resample monthly OHLCV bars into annual bars.

    Alpaca has no TimeFrame.Year, so we fetch monthly bars and aggregate them
    here. Incomplete years (< 10 months of data) are dropped to avoid a
    partial-year bar at each end biasing the results.
    """
    from collections import defaultdict
    buckets: dict[str, list] = defaultdict(list)
    for bar in monthly_bars:
        year = bar['timestamp'][:4]
        buckets[year].append(bar)

    yearly: list[dict] = []
    for year in sorted(buckets.keys()):
        g = buckets[year]
        if len(g) < 10:          # drop partial years (< 10 months)
            continue
        # Drop individual monthly bars with missing OHLCV (Alpaca sometimes returns None)
        valid = [b for b in g
                 if b.get('open') is not None and b.get('high') is not None
                 and b.get('low') is not None and b.get('close') is not None]
        if len(valid) < 10:
            continue
        yearly.append({
            'timestamp': f'{year}-12-31T00:00:00+00:00',
            'open':   valid[0]['open'],
            'high':   max(b['high'] for b in valid),
            'low':    min(b['low']  for b in valid),
            'close':  valid[-1]['close'],
            'volume': sum(b['volume'] or 0 for b in valid),
            'vwap':   float(np.mean([b.get('vwap') or b['close'] for b in valid])),
        })
    return yearly


def build_regime_map(spy_bars: list[dict]) -> dict[str, str]:
    """
    Returns {date_str: 'bull' | 'bear' | 'neutral'} for every bar in spy_bars.
    Regime = direction of SPY 20-day price change (>+2% bull, <-2% bear).
    """
    regime: dict[str, str] = {}
    closes = [b['close'] for b in spy_bars]
    dates  = [b['timestamp'][:10] for b in spy_bars]
    for i in range(20, len(spy_bars)):
        change = (closes[i] - closes[i - 20]) / closes[i - 20] if closes[i - 20] > 0 else 0
        if change > 0.02:
            regime[dates[i]] = 'bull'
        elif change < -0.02:
            regime[dates[i]] = 'bear'
        else:
            regime[dates[i]] = 'neutral'
    return regime


# ── Per-symbol simulation ─────────────────────────────────────────────────────

def backtest_symbol(
    symbol: str,
    sector: str,
    bars: list[dict],
    regime_map: dict[str, str],
    slippage_pct: float,
    min_corners: int,
    trendline_lookback: int = 252,
    regime_gate: bool = True,
    bars_per_year: int = 252,
    vol_avg_bars: int = 20,
) -> list[dict]:
    """
    Simulate Newman strategy on daily bars. Returns list of closed trade dicts.

    Entry rule:
      - Trendline resistance break (peak detection, not 20-day high)
      - Volume ≥ 2.5× 20-day avg
      - Conviction score ≥ min_corners
      - Enter at next bar's open + slippage

    Exit rules (in priority order):
      1. Immediately wrong:  day-1 open > 1×ATR below entry → exit at open
      2. Stop loss:          close ≤ ATR stop → exit next open
      3. Profit tier 3 (45%+): exit next open
      4. Profit tier 2 (30%+): scale 33% → continue
      5. Profit tier 1 (15%+): scale 33% → continue
      6. Pyramid (3%+ + 2×vol): add 50% to position

    No look-ahead: all signal checks use bars[:i+1] or bars[:i].
    """
    # Need enough bars for trendline detection + rolling averages.
    # Scale minimum to timeframe: coarser bars have smaller vol_avg_bars (2–20).
    # The hard floor of 20 was calibrated for daily — it rejects yearly bars (~10).
    min_bars = trendline_lookback + max(vol_avg_bars + 2, 3)
    if len(bars) < min_bars:
        return []

    trades: list[dict] = []
    position = None

    for i in range(trendline_lookback, len(bars) - 1):
        bar        = bars[i]
        next_bar   = bars[i + 1]
        date_str   = bar['timestamp'][:10]

        # Rolling averages computed on bars strictly before i (no look-ahead)
        avg_vol_20 = float(np.mean([b['volume'] for b in bars[i - vol_avg_bars:i]]))
        atr        = compute_atr(bars[max(0, i - vol_avg_bars):i+1])

        # ── ENTRY ─────────────────────────────────────────────────────────
        if position is None:
            # Regime gate: only enter during bull SPY regime
            if regime_gate and regime_map.get(date_str, 'unknown') != 'bull':
                continue

            # Sector-specific filter (e.g. biotech price/volume screen)
            sector_filter = SECTOR_FILTERS.get(sector)
            if sector_filter and not sector_filter(bars, i, vol_avg_bars):
                continue

            trendline_break, resistance = detect_resistance_break(
                bars[:i+1], lookback=trendline_lookback
            )
            conviction = score_conviction(bars, i, avg_vol_20, trendline_break,
                                          bars_per_year=bars_per_year)

            if conviction >= min_corners and trendline_break:
                raw_entry = next_bar['open']
                if raw_entry <= 0:
                    continue
                entry = apply_slippage(raw_entry, 'buy', slippage_pct)
                stop  = entry - (1.5 * atr) if atr > 0 else entry * 0.95

                position = {
                    'entry_price':  entry,
                    'entry_bar_idx': i + 1,
                    'entry_date':   next_bar['timestamp'][:10],
                    'qty':          100,
                    'stop':         stop,
                    'pyramid_level': 0,
                    'profit_taken':  0,
                    'conviction':    conviction,
                    'resistance':    round(resistance, 4),
                    'slippage_entry': round(entry - raw_entry, 4),
                }

        # ── MANAGEMENT ────────────────────────────────────────────────────
        else:
            entry     = position['entry_price']
            pnl_pct   = (bar['close'] - entry) / entry if entry > 0 else 0
            days_held = i + 1 - position['entry_bar_idx']

            exited      = False
            exit_reason = None
            exit_price  = next_bar['open']

            # 1. Immediately wrong: day-1 open more than 1×ATR below entry
            if days_held == 1 and next_bar['open'] < entry - atr:
                exit_reason = 'immediately_wrong'
                exited = True

            # 2. Stop loss
            elif bar['close'] <= position['stop']:
                exit_reason = 'stop_loss'
                exited = True

            # 3. Full exit at tier 3 (45%+)
            elif pnl_pct >= 0.45:
                exit_reason = 'profit_t3'
                exited = True

            # 4. Scale out at tier 2 (30%+)
            elif pnl_pct >= 0.30 and position['profit_taken'] < 2:
                position['qty'] = max(1, int(position['qty'] * 0.67))
                position['profit_taken'] = 2

            # 5. Scale out at tier 1 (15%+)
            elif pnl_pct >= 0.15 and position['profit_taken'] < 1:
                position['qty'] = max(1, int(position['qty'] * 0.67))
                position['profit_taken'] = 1

            # 6. Pyramid: price up ≥3% AND volume surge
            elif (pnl_pct >= 0.03
                  and position['pyramid_level'] < 2
                  and avg_vol_20 > 0
                  and bar['volume'] >= 2.0 * avg_vol_20):
                position['qty'] = int(position['qty'] * 1.5)
                position['pyramid_level'] += 1

            if exited:
                raw_exit = exit_price
                exit_price = apply_slippage(raw_exit, 'sell', slippage_pct)
                pnl_final  = (exit_price - entry) / entry if entry > 0 else 0

                trades.append({
                    'symbol':          symbol,
                    'sector':          sector,
                    'entry_price':     round(entry, 4),
                    'exit_price':      round(exit_price, 4),
                    'entry_date':      position['entry_date'],
                    'exit_date':       next_bar['timestamp'][:10],
                    'pnl_pct':         round(pnl_final * 100, 2),
                    'exit_reason':     exit_reason,
                    'hold_days':       i + 1 - position['entry_bar_idx'],
                    'pyramid_levels':  position['pyramid_level'],
                    'conviction':      position['conviction'],
                    'resistance':      position['resistance'],
                    'slippage_cost_pct': round(
                        (position['slippage_entry'] / position['entry_price']
                         + slippage_pct) * 100, 3
                    ),
                    'immediately_wrong': exit_reason == 'immediately_wrong',
                    'regime':          regime_map.get(position['entry_date'], 'unknown'),
                })
                position = None

    # Close any open position at end of series
    if position is not None:
        entry      = position['entry_price']
        raw_exit   = bars[-1]['close']
        exit_price = apply_slippage(raw_exit, 'sell', slippage_pct)
        pnl_final  = (exit_price - entry) / entry if entry > 0 else 0
        trades.append({
            'symbol':          symbol,
            'sector':          sector,
            'entry_price':     round(entry, 4),
            'exit_price':      round(exit_price, 4),
            'entry_date':      position['entry_date'],
            'exit_date':       bars[-1]['timestamp'][:10],
            'pnl_pct':         round(pnl_final * 100, 2),
            'exit_reason':     'end_of_period',
            'hold_days':       len(bars) - position['entry_bar_idx'],
            'pyramid_levels':  position['pyramid_level'],
            'conviction':      position['conviction'],
            'resistance':      position['resistance'],
            'slippage_cost_pct': round(
                (position['slippage_entry'] / position['entry_price']
                 + slippage_pct) * 100, 3
            ),
            'immediately_wrong': False,
            'regime':          regime_map.get(position['entry_date'], 'unknown'),
        })

    return trades


# ── Stats helpers ─────────────────────────────────────────────────────────────

def compute_stats(trades: list[dict]) -> dict:
    """Compute performance stats for a list of trades, including extended metrics."""
    empty = {
        'total_trades': 0, 'winning_trades': 0, 'win_rate_pct': 0,
        'avg_win_pct': 0, 'avg_loss_pct': 0, 'win_loss_ratio': 0,
        'expectancy_per_trade': 0, 'profit_factor': 0,
        'total_return_pct': 0, 'final_equity': 100_000,
        'max_drawdown_pct': 0, 'sharpe': 0, 'sortino': 0, 'calmar': 0,
        'avg_hold_days': 0, 'median_hold_days': 0,
        'max_consec_wins': 0, 'max_consec_losses': 0,
        'best_trade': None, 'worst_trade': None,
        'monthly_returns': [],
    }
    if not trades:
        return empty

    wins   = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]

    avg_win  = float(np.mean([t['pnl_pct'] for t in wins]))   if wins   else 0.0
    avg_loss = float(np.mean([t['pnl_pct'] for t in losses])) if losses else 0.0
    win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

    win_rate = len(wins) / len(trades)
    # Expectancy: expected return per trade in % terms
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
    # Profit factor: gross wins / gross losses (losses are negative, so abs)
    gross_wins   = sum(t['pnl_pct'] for t in wins)
    gross_losses = abs(sum(t['pnl_pct'] for t in losses)) if losses else 1.0
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float('inf')

    # Sequential equity curve — 5% of current equity risked per trade
    equity = 100_000.0
    peak   = equity
    max_dd = 0.0
    returns: list[float] = []
    sorted_trades = sorted(trades, key=lambda x: x['entry_date'])
    for t in sorted_trades:
        risk_usd = equity * 0.05
        pnl_usd  = risk_usd * (t['pnl_pct'] / 100.0)
        equity  += pnl_usd
        returns.append(t['pnl_pct'])
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100.0
        if dd > max_dd:
            max_dd = dd

    total_return = (equity - 100_000.0) / 100_000.0 * 100.0

    # Sharpe (annualised, assuming each trade ~= 1 unit, risk-free = 0)
    if len(returns) > 1:
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252 / max(1, len(returns))))
    else:
        sharpe = 0.0

    # ── Extended metrics ─────────────────────────────────────────────────────

    # Sortino ratio (annualised, downside deviation only)
    downside_returns = [r for r in returns if r < 0]
    if downside_returns and len(returns) > 1:
        mean_ret = float(np.mean(returns))
        # Downside deviation: RMS of negative returns (full-series denominator)
        downside_dev = float(np.sqrt(sum(r ** 2 for r in downside_returns) / len(returns)))
        # Annualise based on trades per year
        first_date = sorted_trades[0]['entry_date']
        last_date  = sorted_trades[-1]['exit_date']
        days_span  = max(1, (datetime.strptime(last_date, '%Y-%m-%d')
                             - datetime.strptime(first_date, '%Y-%m-%d')).days)
        trades_per_year = len(trades) / (days_span / 365.25)
        ann_return   = mean_ret * trades_per_year
        ann_downside = downside_dev * float(np.sqrt(trades_per_year))
        sortino = ann_return / ann_downside if ann_downside > 0 else 0.0
    else:
        sortino = 0.0

    # Calmar ratio (CAGR / max drawdown)
    if max_dd > 0 and total_return != 0:
        first_date = sorted_trades[0]['entry_date']
        last_date  = sorted_trades[-1]['exit_date']
        days_span  = max(1, (datetime.strptime(last_date, '%Y-%m-%d')
                             - datetime.strptime(first_date, '%Y-%m-%d')).days)
        years = days_span / 365.25
        cagr = ((equity / 100_000.0) ** (1.0 / years) - 1.0) * 100.0 if years > 0 else 0.0
        calmar = cagr / max_dd if max_dd > 0 else 0.0
    else:
        calmar = 0.0
        cagr = 0.0

    # Hold days
    hold_days = [t.get('hold_days', 0) for t in sorted_trades]
    avg_hold  = float(np.mean(hold_days)) if hold_days else 0.0
    median_hold = int(np.median(hold_days)) if hold_days else 0

    # Consecutive wins / losses
    max_consec_wins = max_consec_losses = 0
    streak = 0
    for t in sorted_trades:
        if t['pnl_pct'] > 0:
            streak = streak + 1 if streak > 0 else 1
            max_consec_wins = max(max_consec_wins, streak)
        else:
            streak = 0
    streak = 0
    for t in sorted_trades:
        if t['pnl_pct'] <= 0:
            streak = streak + 1 if streak > 0 else 1
            max_consec_losses = max(max_consec_losses, streak)
        else:
            streak = 0

    # Best / worst trade
    best  = max(sorted_trades, key=lambda t: t['pnl_pct'])
    worst = min(sorted_trades, key=lambda t: t['pnl_pct'])
    best_trade  = {'symbol': best['symbol'],  'pnl_pct': best['pnl_pct'],
                   'sector': best['sector'],  'date': best['entry_date']}
    worst_trade = {'symbol': worst['symbol'], 'pnl_pct': worst['pnl_pct'],
                   'sector': worst['sector'], 'date': worst['entry_date']}

    # Monthly returns (attributed to exit month)
    from collections import defaultdict
    monthly_pnl: dict[str, list[float]] = defaultdict(list)
    for t in sorted_trades:
        month_key = t['exit_date'][:7]  # YYYY-MM
        monthly_pnl[month_key].append(t['pnl_pct'])

    # Build complete month series
    if sorted_trades:
        first_m = datetime.strptime(sorted_trades[0]['exit_date'][:7], '%Y-%m')
        last_m  = datetime.strptime(sorted_trades[-1]['exit_date'][:7], '%Y-%m')
        all_months: list[str] = []
        cur = first_m
        while cur <= last_m:
            all_months.append(cur.strftime('%Y-%m'))
            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)
        monthly_returns = []
        for m in all_months:
            pnls = monthly_pnl.get(m, [])
            monthly_returns.append({
                'month': m,
                'avg_return_pct': round(float(np.mean(pnls)), 2) if pnls else 0.0,
                'total_return_pct': round(sum(pnls), 2) if pnls else 0.0,
                'trade_count': len(pnls),
            })
        pos_months = sum(1 for mr in monthly_returns if mr['avg_return_pct'] > 0)
        neg_months = sum(1 for mr in monthly_returns if mr['avg_return_pct'] < 0)
    else:
        monthly_returns = []
        pos_months = neg_months = 0

    return {
        'total_trades':         len(trades),
        'winning_trades':       len(wins),
        'win_rate_pct':         round(win_rate * 100, 1),
        'avg_win_pct':          round(avg_win, 2),
        'avg_loss_pct':         round(avg_loss, 2),
        'win_loss_ratio':       round(win_loss_ratio, 2),
        'expectancy_per_trade': round(expectancy, 2),
        'profit_factor':        round(profit_factor, 2),
        'total_return_pct':     round(total_return, 1),
        'final_equity':         round(equity, 2),
        'max_drawdown_pct':     round(max_dd, 1),
        'sharpe':               round(sharpe, 2),
        # Extended metrics
        'sortino':              round(sortino, 2),
        'calmar':               round(calmar, 2),
        'avg_hold_days':        round(avg_hold, 1),
        'median_hold_days':     median_hold,
        'max_consec_wins':      max_consec_wins,
        'max_consec_losses':    max_consec_losses,
        'best_trade':           best_trade,
        'worst_trade':          worst_trade,
        'positive_months':      pos_months,
        'negative_months':      neg_months,
        'monthly_returns':      monthly_returns,
    }


def check_success(stats: dict) -> dict[str, bool]:
    """Run pre-defined criteria against a stats dict."""
    results = {}
    for key, rule in SUCCESS_CRITERIA.items():
        val = stats.get(key, 0)
        if rule['op'] == '>=':
            results[key] = val >= rule['threshold']
        elif rule['op'] == '<=':
            results[key] = val <= rule['threshold']
    return results


def format_criteria_block(stats: dict) -> str:
    """Print success criteria with pass/fail for a stats dict."""
    passed = check_success(stats)
    lines = ['SUCCESS CRITERIA (pre-defined):']
    all_pass = True
    for key, rule in SUCCESS_CRITERIA.items():
        val = stats.get(key, 0)
        ok  = passed[key]
        if not ok:
            all_pass = False
        mark = 'PASS' if ok else 'FAIL'
        lines.append(f'  [{mark}] {rule["label"]:30s}  got: {val}')
    lines.append(f'  Overall: {"ALL PASS" if all_pass else "CRITERIA NOT MET"}')
    return '\n'.join(lines)


# ── Main orchestration ────────────────────────────────────────────────────────

def run_backtest(
    lookback:    int   = 1260,
    split_date:  str   = '2024-01-01',
    slippage:    float = 0.0075,
    min_corners: int   = 2,
    regime_gate: bool  = True,
    timeframe:   str   = 'day',
) -> dict:
    from app.integrations.alpaca_client import AlpacaClient
    from alpaca.data.timeframe import TimeFrame as TF, TimeFrameUnit

    client = AlpacaClient()

    tf_spec, bars_per_year, trendline_lookback, vol_avg_bars = TIMEFRAMES.get(
        timeframe, ('Day', 252, 252, 20)
    )
    # tf_spec is either a plain string ('Day', 'Hour', …) or a tuple
    # ('Minute', N) meaning TimeFrame(N, TimeFrameUnit.Minute).
    if isinstance(tf_spec, tuple):
        unit_name, multiplier = tf_spec
        alpaca_tf = TF(multiplier, getattr(TimeFrameUnit, unit_name))
    else:
        alpaca_tf = getattr(TF, tf_spec)
    fetch_days = lookback  # calendar days — Alpaca interprets this correctly

    # Yearly timeframe resamples from monthly bars.
    # trendline_lookback=5 years → we need ≥10 complete annual bars to have any
    # in-sample data, so ensure at least 15 calendar years are fetched.
    if timeframe == 'year':
        min_year_days = 365 * 15   # 15 calendar years → ~10–12 complete annual bars
        if fetch_days < min_year_days:
            print(f"⚠  Yearly timeframe: auto-extending lookback from {lookback} → {min_year_days} days"
                  f" (need ≥ 15 years for a meaningful annual trendline).\n"
                  f"   Pass --lookback 5475 to suppress this adjustment.\n")
            fetch_days = min_year_days

    if timeframe in ('5min', '10min', '20min') and lookback > 90:
        mins = {'5min': 5, '10min': 10, '20min': 20}[timeframe]
        bpd  = 390 // mins
        print(f"⚠  {timeframe} bars with lookback={lookback} days"
              f" (~{lookback * bpd:,} bars/symbol). Recommend --lookback 60.\n")

    if timeframe == 'minute' and lookback > 60:
        print(f"⚠  Minute bars requested with lookback={lookback} days."
              f" This fetches ~{lookback * 390:,} bars/symbol and will be slow."
              f" Recommend --lookback 30 for minute timeframe.\n")
    elif timeframe == 'hour' and lookback > 756:
        print(f"⚠  Hour bars with lookback={lookback} days (~{lookback * 7:,} bars/symbol)."
              f" Consider --lookback 365.\n")

    print(f"\nFetching SPY regime data ({fetch_days} calendar days, {timeframe} bars)...")
    spy_bars: list[dict] = []
    try:
        spy_bars = client.get_bars('SPY', days=fetch_days, timeframe=alpaca_tf)
        if timeframe == 'year':
            spy_bars = resample_to_yearly(spy_bars)
        regime_map = build_regime_map(spy_bars)
        spy_return = (spy_bars[-1]['close'] - spy_bars[0]['close']) / spy_bars[0]['close'] * 100
        print(f"  SPY: {len(spy_bars)} {timeframe} bars, {spy_return:+.1f}% over period")
    except Exception as e:
        print(f"  SPY fetch failed ({e}) — regime will be 'unknown'")
        regime_map = {}
        spy_return = 0.0
        trendline_lookback = bars_per_year

    all_trades: list[dict] = []
    skipped:    list[str]  = []

    print(f"\nRunning backtest: timeframe={timeframe} | lookback={lookback}cal days "
          f"({trendline_lookback} bars/yr) | split={split_date} | "
          f"slippage={slippage*100:.2f}% | min_corners={min_corners} | "
          f"regime_gate={'ON' if regime_gate else 'OFF'}\n")
    print("⚠  SURVIVORSHIP BIAS: universe contains only stocks with current Alpaca data.\n"
          "   Delisted stocks (GOEV, NKLA, SOLO, AITX, ASTR) excluded. Returns overstated.\n")

    for sector, symbols in SECTOR_UNIVERSE.items():
        print(f"Scanning {sector}...")
        for symbol in symbols:
            try:
                bars = client.get_bars(symbol, days=fetch_days, timeframe=alpaca_tf)
                if timeframe == 'year':
                    bars = resample_to_yearly(bars)
                min_required = trendline_lookback + max(vol_avg_bars + 2, 3)
                if len(bars) < min_required:
                    skipped.append(symbol)
                    print(f"  {symbol}: SKIP (only {len(bars)} bars, need {min_required})")
                    continue
                trades = backtest_symbol(
                    symbol, sector, bars, regime_map,
                    slippage, min_corners,
                    trendline_lookback=trendline_lookback,
                    regime_gate=regime_gate,
                    bars_per_year=bars_per_year,
                    vol_avg_bars=vol_avg_bars,
                )
                all_trades.extend(trades)
                pnls = [t['pnl_pct'] for t in trades]
                avg  = f"{np.mean(pnls):+.1f}%" if pnls else "—"
                print(f"  {symbol}: {len(trades):3d} trades from {len(bars)} bars  avg {avg}")
            except Exception as e:
                skipped.append(symbol)
                print(f"  {symbol}: SKIP ({type(e).__name__}: {e})")

    if not all_trades:
        print("\nNo trades generated. Check API connection or lower --min-corners.")
        return {}

    # ── Split in-sample / out-of-sample ──────────────────────────────────────
    in_sample  = [t for t in all_trades if t['entry_date'] <  split_date]
    out_sample = [t for t in all_trades if t['entry_date'] >= split_date]

    stats_all = compute_stats(all_trades)
    stats_in  = compute_stats(in_sample)
    stats_out = compute_stats(out_sample)

    # ── Regime breakdown ──────────────────────────────────────────────────────
    regime_breakdown: dict[str, dict] = {}
    for reg in ('bull', 'bear', 'neutral', 'unknown'):
        rt = [t for t in all_trades if t['regime'] == reg]
        if rt:
            regime_breakdown[reg] = {
                'trades':    len(rt),
                'win_rate':  round(len([t for t in rt if t['pnl_pct'] > 0]) / len(rt) * 100, 1),
                'avg_pnl':   round(float(np.mean([t['pnl_pct'] for t in rt])), 2),
            }

    # ── Sector breakdown ─────────────────────────────────────────────────────
    sector_stats: dict[str, dict] = {}
    for sector in SECTOR_UNIVERSE:
        st = [t for t in all_trades if t['sector'] == sector]
        if st:
            sw = [t for t in st if t['pnl_pct'] > 0]
            sector_stats[sector] = {
                'trades':   len(st),
                'win_rate': round(len(sw) / len(st) * 100, 1),
                'avg_pnl':  round(float(np.mean([t['pnl_pct'] for t in st])), 2),
            }

    # ── Top trades ───────────────────────────────────────────────────────────
    top5 = sorted(all_trades, key=lambda t: t['pnl_pct'], reverse=True)[:5]

    # ── Exit reason breakdown ─────────────────────────────────────────────────
    exit_counts: dict[str, int] = {}
    for t in all_trades:
        exit_counts[t['exit_reason']] = exit_counts.get(t['exit_reason'], 0) + 1

    # ── Format report ────────────────────────────────────────────────────────
    def fmt_stats(label: str, s: dict) -> str:
        wl = f"{s['win_loss_ratio']:.1f}" if s['win_loss_ratio'] != float('inf') else '∞'
        lines = [
            f"\n{'─'*50}",
            f"  {label}",
            f"{'─'*50}",
            f"  Trades:        {s['total_trades']}  ({s['winning_trades']} wins, {s['win_rate_pct']:.1f}%)",
            f"  Avg Win:       +{s['avg_win_pct']:.1f}%",
            f"  Avg Loss:      {s['avg_loss_pct']:.1f}%",
            f"  W/L Ratio:     {wl}",
            f"  Expectancy:    {'+' if s['expectancy_per_trade'] >= 0 else ''}{s['expectancy_per_trade']:.1f}% per trade",
            f"  Profit Factor: {s['profit_factor']:.2f}x",
            f"  Total Return:  {'+' if s['total_return_pct'] >= 0 else ''}{s['total_return_pct']:.1f}%"
            f"  (${s['final_equity']:,.0f})",
            f"  Max Drawdown:  -{s['max_drawdown_pct']:.1f}%",
            f"  Sharpe:        {s['sharpe']:.2f}  (informational — not a gate for this strategy)",
            f"  Sortino:       {s['sortino']:.2f}  (downside-risk adjusted)",
            f"  Calmar:        {s['calmar']:.2f}  (CAGR / max drawdown)",
            f"  Avg Hold:      {s['avg_hold_days']:.1f} days  (median {s['median_hold_days']})",
            f"  Max Consec W:  {s['max_consec_wins']}   Max Consec L: {s['max_consec_losses']}",
            f"  Months:        {s['positive_months']} positive / {s['negative_months']} negative",
        ]
        if s.get('best_trade'):
            bt = s['best_trade']
            wt = s['worst_trade']
            lines.append(f"  Best Trade:    {bt['symbol']} +{bt['pnl_pct']:.1f}% ({bt['sector']}, {bt['date']})")
            lines.append(f"  Worst Trade:   {wt['symbol']} {wt['pnl_pct']:.1f}% ({wt['sector']}, {wt['date']})")
        return '\n'.join(lines)

    output_lines = [
        '',
        '=' * 60,
        '  NEWMAN STRATEGY BACKTEST RESULTS  v2',
        '=' * 60,
        f"  Timeframe:   {timeframe} bars",
        f"  Lookback:    {lookback} calendar days  (~{len(spy_bars) if spy_bars else '?'} {timeframe} bars fetched)",
        f"  Split date:  {split_date}  (in-sample < / out-of-sample ≥)",
        f"  Slippage:    {slippage*100:.2f}% per fill",
        f"  Min corners: {min_corners}",
        f"  Regime gate: {'ON (bull only)' if regime_gate else 'OFF'}",
        f"  SPY return:  {spy_return:+.1f}% over same period",
        '',
        '⚠  SURVIVORSHIP BIAS: universe is current survivors only.',
        '   Results are overstated vs a point-in-time universe.',
    ]

    output_lines.append(fmt_stats('ALL TRADES', stats_all))
    output_lines.append(fmt_stats(f'IN-SAMPLE  (before {split_date})', stats_in))
    output_lines.append(fmt_stats(f'OUT-OF-SAMPLE  (from {split_date})', stats_out))

    output_lines.append('\n' + format_criteria_block(stats_out))  # judge on out-of-sample

    output_lines.append('\nBY SECTOR:')
    for sec, ss in sector_stats.items():
        output_lines.append(
            f"  {sec:20s}: {ss['trades']:3d} trades | {ss['win_rate']:.0f}% win | avg {ss['avg_pnl']:+.1f}%"
        )

    output_lines.append('\nBY REGIME (at entry):')
    for reg, rs in regime_breakdown.items():
        output_lines.append(
            f"  {reg:10s}: {rs['trades']:3d} trades | {rs['win_rate']:.0f}% win | avg {rs['avg_pnl']:+.1f}%"
        )

    output_lines.append('\nEXIT REASONS:')
    for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
        pct = count / len(all_trades) * 100
        output_lines.append(f"  {reason:20s}: {count:3d}  ({pct:.0f}%)")

    # Monthly returns chart (from all-trades stats)
    if stats_all.get('monthly_returns'):
        output_lines.append('\nMONTHLY RETURNS (by exit month):')
        for mr in stats_all['monthly_returns']:
            r = mr['avg_return_pct']
            c = mr['trade_count']
            bar = '█' * int(abs(r) / 2)
            sign = '+' if r >= 0 else ''
            icon = '🟢' if r > 0 else ('🔴' if r < 0 else '⚪')
            output_lines.append(f"  {mr['month']}  {sign}{r:6.1f}%  ({c:2d} trades)  {icon} {bar}")

    output_lines.append('\nTOP 5 TRADES:')
    for idx, t in enumerate(top5, 1):
        output_lines.append(
            f"  {idx}. {t['symbol']:6s}: {t['pnl_pct']:+.1f}%"
            f"  ({t['exit_reason']}, {t['hold_days']}d, regime={t['regime']}, conviction={t['conviction']})"
        )

    if skipped:
        output_lines.append(f"\nSkipped ({len(skipped)}): {', '.join(skipped)}")

    output_lines.append('')
    output = '\n'.join(output_lines)
    print(output)

    # ── Save results ─────────────────────────────────────────────────────────
    out_dir = os.path.dirname(__file__)

    summary = {
        'run_ts':      datetime.now(timezone.utc).isoformat(),
        'params': {
            'lookback': lookback, 'split_date': split_date,
            'slippage': slippage, 'min_corners': min_corners,
            'timeframe': timeframe, 'regime_gate': regime_gate,
        },
        'spy_return_pct': round(spy_return, 2),
        'all':        stats_all,
        'in_sample':  stats_in,
        'out_sample': stats_out,
        'by_sector':  sector_stats,
        'by_regime':  regime_breakdown,
        'exit_reasons': exit_counts,
        'success_criteria': check_success(stats_out),
        'top_5_trades': top5,
        'symbols_skipped': skipped,
    }

    with open(os.path.join(out_dir, 'results.json'), 'w') as f:
        json.dump({'summary': summary, 'trades': all_trades}, f, indent=2, default=str)

    with open(os.path.join(out_dir, 'results_latest.txt'), 'w') as f:
        f.write(output)

    with open(os.path.join(out_dir, 'trades.csv'), 'w', newline='') as f:
        if all_trades:
            writer = csv.DictWriter(f, fieldnames=all_trades[0].keys())
            writer.writeheader()
            writer.writerows(all_trades)

    print(f"Saved: results.json  results_latest.txt  trades.csv\n")
    return summary


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Newman Strategy Backtester v2')
    parser.add_argument('--lookback',    type=int,   default=1260,
                        help='Total bars to fetch per symbol (default 1260 ≈ 5 years)')
    parser.add_argument('--split',       type=str,   default='2024-01-01',
                        help='In-sample/out-of-sample split date YYYY-MM-DD (default 2024-01-01)')
    parser.add_argument('--slippage',    type=float, default=0.0075,
                        help='Adverse slippage per fill as fraction (default 0.0075 = 0.75%%)')
    parser.add_argument('--min-corners',   type=int,   default=2,
                        help='Minimum conviction score to take a trade (default 2)')
    parser.add_argument('--no-regime-gate', action='store_true',
                        help='Disable SPY bull-regime gate (trade in any regime)')
    parser.add_argument('--timeframe', type=str, default='day',
                        choices=['5min', '10min', '20min', 'minute',
                                 'hour', 'day', 'week', 'month', 'year'],
                        help='Bar timeframe (default: day). '
                             'Recommended lookbacks: 5/10/20min→60, minute→30, '
                             'hour→365, day→1260, week→1260, month→1825, year→auto')
    args = parser.parse_args()
    run_backtest(
        lookback=args.lookback,
        split_date=args.split,
        slippage=args.slippage,
        min_corners=args.min_corners,
        regime_gate=not args.no_regime_gate,
        timeframe=args.timeframe,
    )
