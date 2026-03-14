#!/usr/bin/env python3
"""
Golden Strategy Backtester — Proxy-based historical backtest

The live Golden strategy uses SEC 13F + ARK holdings for conviction scoring,
but those aren't available historically. This backtester uses PROXY signals:

  1. SPY correction_score — drawdown from 52-week high (historically testable)
  2. Sector ETF momentum  — proxy for institutional interest in Golden sectors
  3. Volume acceleration   — surge detection same as Newman, Golden's sectors
  4. Price-to-52-week-low  — lower = better entry (correction buying thesis)

Golden Strategy rules applied:
  - Entry: SPY correction window + sector momentum + volume surge + depressed price
  - Sectors: AI infra, quantum, defense tech, energy transition, biotech, space
  - Position sizing: High conviction=20%, Medium=10%, Exploratory=5% of portfolio
  - Price gates: Under $20 always, $20-100 high conviction only, >$100 blocked
  - Stop loss: 25% thesis-driven floor OR 3×ATR (whichever is tighter)
  - 72h cooldown after stop-out (3 trading days)
  - Max 10 concurrent positions
  - Exit: 50%+ profit take, or thesis invalidation (stop)

SURVIVORSHIP BIAS WARNING:
  This universe contains only stocks that survived to today with Alpaca data.
  Results are overstated vs a point-in-time universe.
"""
import sys, os, argparse, json, csv, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

from datetime import datetime, timezone
from collections import defaultdict
import numpy as np

logging.basicConfig(level=logging.WARNING)

# ── Timeframe configs (same structure as Newman) ─────────────────────────────
TIMEFRAMES = {
    '5min':   (('Minute',  5), 19_656,   390,  78),
    '10min':  (('Minute', 10),  9_828,   195,  39),
    '20min':  (('Minute', 20),  4_914,   100,  20),
    'minute': ('Minute',        98_280, 1_950, 390),
    'hour':   ('Hour',           1_638,   130,  33),
    'day':    ('Day',              252,   252,  20),
    'week':   ('Week',              52,    52,   4),
    'month':  ('Month',             12,    36,   3),
}

# ── Golden Sector Universe ───────────────────────────────────────────────────
# Maps Golden sectors → tradeable tickers + sector ETF proxy for momentum scoring
#
# Sector ETFs used for momentum proxy (not traded directly):
#   AI/Semiconductors: SOXX, Quantum: (no pure ETF, use QTUM), Defense: ITA,
#   Energy transition: ICLN/TAN, Biotech: XBI, Space: UFO/ARKX
GOLDEN_UNIVERSE = {
    'ai_infrastructure': {
        'etf': 'SOXX',
        'tickers': ['NVDA', 'AMD', 'SMCI', 'MRVL', 'ON', 'PLTR', 'SOUN', 'BBAI',
                     'CORZ', 'IREN', 'APLD', 'LITE'],
    },
    'quantum_computing': {
        'etf': 'SOXX',  # no pure quantum ETF; SOXX closest proxy
        'tickers': ['IONQ', 'RGTI', 'QUBT', 'QBTS', 'ARQQ'],
    },
    'defense_tech': {
        'etf': 'ITA',
        'tickers': ['LMT', 'RTX', 'NOC', 'GD', 'PLTR', 'KTOS', 'RKLB'],
    },
    'energy_transition': {
        'etf': 'ICLN',
        'tickers': ['UEC', 'UUUU', 'DNN', 'CCJ', 'NXE', 'BE', 'FSLR'],
    },
    'biotech_platforms': {
        'etf': 'XBI',
        'tickers': ['GERN', 'BCRX', 'ADMA', 'SIGA', 'TGTX', 'AGEN', 'RCUS', 'RXRX', 'CLOV'],
    },
    'space': {
        'etf': 'ITA',  # ARKX is ARK-managed, ITA as defense/aero proxy
        'tickers': ['RKLB', 'SPCE', 'ASTS'],
    },
}

# Flatten for quick lookup
ALL_TICKERS = set()
TICKER_TO_SECTOR: dict[str, str] = {}
for _sec, _cfg in GOLDEN_UNIVERSE.items():
    for _t in _cfg['tickers']:
        ALL_TICKERS.add(_t)
        TICKER_TO_SECTOR[_t] = _sec

SECTOR_ETFS = {sec: cfg['etf'] for sec, cfg in GOLDEN_UNIVERSE.items()}
UNIQUE_ETFS = list(set(SECTOR_ETFS.values()))

# ── Success Criteria (calibrated for correction-buying strategy) ─────────────
# Golden is a different beast than Newman: fewer trades, longer holds, wider stops.
# Expectancy should be positive, profit factor > 1.5, drawdown controlled.
SUCCESS_CRITERIA = {
    'expectancy_per_trade': {'threshold': 5.0,  'op': '>=', 'label': 'Expectancy/trade ≥ +5%'},
    'win_loss_ratio':       {'threshold': 2.0,  'op': '>=', 'label': 'Avg W / Avg L ≥ 2.0'},
    'profit_factor':        {'threshold': 1.5,  'op': '>=', 'label': 'Profit factor ≥ 1.5'},
    'max_drawdown_pct':     {'threshold': 30.0, 'op': '<=', 'label': 'Max drawdown ≤ 30%'},
    'total_trades':         {'threshold': 10,   'op': '>=', 'label': 'Trade count ≥ 10'},
}

# ── Max concurrent positions (Golden rule) ───────────────────────────────────
MAX_CONCURRENT = 10

# ── Cooldown after stop-out (3 trading days ≈ 72h) ──────────────────────────
COOLDOWN_BARS = 3  # for daily; scaled for other timeframes


# ── Core signal functions ─────────────────────────────────────────────────────

def compute_atr(bars: list[dict], period: int = 14) -> float:
    """ATR-14 using Wilder's smoothing."""
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]['high'], bars[i]['low'], bars[i - 1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return trs[-1] if trs else 0.0
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return float(atr)


def compute_spy_correction_score(spy_bars: list[dict], i: int,
                                  bars_per_year: int = 252) -> int:
    """
    Compute correction_score (0-100) from SPY drawdown vs 52-week high.
    Same logic as golden_scanner.compute_correction_score but historical.

    Score mapping:
      0-20  = SPY near highs (bad entry window)
      20-40 = mild pullback 2-5%
      40-60 = moderate correction 5-10% (entry unlocked)
      60-80 = significant correction 10-15%
      80-100 = deep correction/bear >15% (ideal entry)
    """
    lookback = min(i, bars_per_year)
    if lookback < 20:
        return 0

    spy_price = spy_bars[i]['close']
    spy_52w_high = max(b['high'] for b in spy_bars[i - lookback:i + 1])

    if spy_52w_high <= 0:
        return 0

    drawdown_pct = (spy_price - spy_52w_high) / spy_52w_high  # negative
    abs_dd = abs(drawdown_pct)

    if abs_dd < 0.02:
        return int(abs_dd / 0.02 * 20)
    elif abs_dd < 0.05:
        return 20 + int((abs_dd - 0.02) / 0.03 * 20)
    elif abs_dd < 0.10:
        return 40 + int((abs_dd - 0.05) / 0.05 * 20)
    elif abs_dd < 0.15:
        return 60 + int((abs_dd - 0.10) / 0.05 * 20)
    else:
        return min(100, 80 + int((abs_dd - 0.15) / 0.10 * 20))


def compute_sector_momentum(etf_bars: list[dict], i: int,
                             lookback: int = 20) -> float:
    """
    Sector ETF momentum: % change over lookback bars.
    Positive = sector trending up (institutional interest proxy).
    """
    if i < lookback:
        return 0.0
    old_close = etf_bars[i - lookback]['close']
    if old_close <= 0:
        return 0.0
    return (etf_bars[i]['close'] - old_close) / old_close


def compute_volume_accel(bars: list[dict], i: int, vol_avg_bars: int = 20) -> float:
    """
    Volume acceleration: current volume / average volume over vol_avg_bars.
    >2.0 = significant volume surge.
    """
    if i < vol_avg_bars:
        return 1.0
    avg_vol = float(np.mean([b['volume'] for b in bars[i - vol_avg_bars:i]]))
    if avg_vol <= 0:
        return 1.0
    return bars[i]['volume'] / avg_vol


def compute_price_depression(bars: list[dict], i: int,
                              bars_per_year: int = 252) -> float:
    """
    Price-to-52-week-low ratio. Lower = more depressed = better entry.
    Returns ratio: 1.0 = at the low, 2.0 = 100% above the low, etc.
    """
    lookback = min(i, bars_per_year)
    if lookback < 20:
        return 999.0
    low_52w = min(b['low'] for b in bars[i - lookback:i + 1])
    if low_52w <= 0:
        return 999.0
    return bars[i]['close'] / low_52w


def score_golden_conviction(
    correction_score: int,
    sector_momentum: float,
    volume_accel: float,
    price_depression: float,
    price: float,
) -> tuple[float, str]:
    """
    Proxy conviction scoring for Golden strategy.

    Returns (score 0.0-1.0, tier).

    Components (weighted):
      - correction_score (0-100 → 0-1): weight 0.30
      - sector_momentum (positive = good): weight 0.25
      - volume_acceleration (>2x = signal): weight 0.20
      - price_depression (closer to 52w low = better): weight 0.15
      - price_fit (under $20 ideal): weight 0.10
    """
    # Correction component
    c_correction = min(1.0, correction_score / 80.0)  # 80+ = full score

    # Sector momentum: positive momentum is good, cap at +10%
    c_momentum = min(1.0, max(0.0, sector_momentum / 0.10))

    # Volume: >2.5x = full score
    c_volume = min(1.0, max(0.0, (volume_accel - 1.0) / 1.5))

    # Depression: ratio of 1.0 (at low) → score 1.0, ratio 2.0+ → score 0.0
    c_depression = max(0.0, min(1.0, 1.0 - (price_depression - 1.0)))

    # Price fit
    if price <= 20.0:
        c_price = 1.0
    elif price <= 100.0:
        c_price = max(0.0, 1.0 - (price - 20.0) / 80.0)
    else:
        c_price = 0.0

    score = (
        c_correction * 0.30 +
        c_momentum   * 0.25 +
        c_volume     * 0.20 +
        c_depression * 0.15 +
        c_price      * 0.10
    )

    # Tier mapping (same as GoldenStrategy.conviction_tier)
    if score >= 0.75:
        tier = 'high'
    elif score >= 0.50:
        tier = 'medium'
    elif score >= 0.30:
        tier = 'exploratory'
    else:
        tier = 'pass'

    return score, tier


def price_passes(price: float, conviction_score: float) -> bool:
    """Golden price gate: <$20 always, $20-$100 high conviction only, >$100 blocked."""
    if price <= 20.0:
        return True
    if price <= 100.0 and conviction_score >= 0.75:
        return True
    return False


def position_size_pct(tier: str) -> float:
    """Portfolio % for each conviction tier."""
    return {'high': 0.20, 'medium': 0.10, 'exploratory': 0.05}.get(tier, 0.0)


def apply_slippage(price: float, side: str, slippage_pct: float) -> float:
    """Adverse slippage: buys fill higher, sells fill lower."""
    if side == 'buy':
        return price * (1.0 + slippage_pct)
    return price * (1.0 - slippage_pct)


def build_regime_map(spy_bars: list[dict]) -> dict[str, str]:
    """
    {date_str: 'bull' | 'bear' | 'neutral'} from SPY 20-bar price change.
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


# ── Build SPY date→index map for cross-referencing ──────────────────────────

def build_spy_date_map(spy_bars: list[dict]) -> dict[str, int]:
    """Map date strings to SPY bar indices for cross-referencing."""
    return {b['timestamp'][:10]: idx for idx, b in enumerate(spy_bars)}


# ── Portfolio-level simulation ────────────────────────────────────────────────

def run_golden_backtest(
    lookback:    int   = 1260,
    split_date:  str   = '2024-01-01',
    slippage:    float = 0.0075,
    timeframe:   str   = 'day',
) -> dict:
    from app.integrations.alpaca_client import AlpacaClient
    from alpaca.data.timeframe import TimeFrame as TF, TimeFrameUnit

    client = AlpacaClient()

    tf_spec, bars_per_year, trendline_lookback, vol_avg_bars = TIMEFRAMES.get(
        timeframe, ('Day', 252, 252, 20)
    )

    if isinstance(tf_spec, tuple):
        unit_name, multiplier = tf_spec
        alpaca_tf = TF(multiplier, getattr(TimeFrameUnit, unit_name))
    else:
        alpaca_tf = getattr(TF, tf_spec)

    fetch_days = lookback
    cooldown_bars = max(1, int(COOLDOWN_BARS * (252 / bars_per_year)))

    print(f"\n{'='*60}")
    print(f"  GOLDEN STRATEGY PROXY BACKTEST")
    print(f"{'='*60}")
    print(f"  Timeframe:   {timeframe} bars")
    print(f"  Lookback:    {lookback} calendar days")
    print(f"  Split date:  {split_date}")
    print(f"  Slippage:    {slippage*100:.2f}% per fill")
    print(f"  Max positions: {MAX_CONCURRENT}")
    print(f"  Cooldown:    {cooldown_bars} bars after stop-out")
    print(f"\n⚠  SURVIVORSHIP BIAS: universe contains only current survivors.")
    print(f"   PROXY SCORING: No historical 13F/ARK data — using momentum/volume/depression proxies.\n")

    # ── Fetch SPY for correction scoring and regime map ──────────────────
    print(f"Fetching SPY ({fetch_days} calendar days, {timeframe} bars)...")
    spy_bars: list[dict] = []
    try:
        spy_bars = client.get_bars('SPY', days=fetch_days, timeframe=alpaca_tf)
        regime_map = build_regime_map(spy_bars)
        spy_date_map = build_spy_date_map(spy_bars)
        spy_return = (spy_bars[-1]['close'] - spy_bars[0]['close']) / spy_bars[0]['close'] * 100
        print(f"  SPY: {len(spy_bars)} bars, {spy_return:+.1f}% over period")
    except Exception as e:
        print(f"  SPY fetch failed ({e}) — will run without correction scoring")
        regime_map = {}
        spy_date_map = {}
        spy_return = 0.0

    # ── Fetch sector ETFs ────────────────────────────────────────────────
    etf_bars_map: dict[str, list[dict]] = {}
    print(f"\nFetching sector ETFs: {', '.join(UNIQUE_ETFS)}...")
    for etf in UNIQUE_ETFS:
        try:
            etf_bars_map[etf] = client.get_bars(etf, days=fetch_days, timeframe=alpaca_tf)
            print(f"  {etf}: {len(etf_bars_map[etf])} bars")
        except Exception as e:
            print(f"  {etf}: SKIP ({e})")
            etf_bars_map[etf] = []

    # Build ETF date→index maps
    etf_date_maps: dict[str, dict[str, int]] = {}
    for etf, bars in etf_bars_map.items():
        etf_date_maps[etf] = {b['timestamp'][:10]: idx for idx, b in enumerate(bars)}

    # ── Fetch all stock bars ─────────────────────────────────────────────
    stock_bars_map: dict[str, list[dict]] = {}
    stock_date_maps: dict[str, dict[str, int]] = {}
    skipped: list[str] = []

    print(f"\nFetching {len(ALL_TICKERS)} stock symbols...")
    for symbol in sorted(ALL_TICKERS):
        try:
            bars = client.get_bars(symbol, days=fetch_days, timeframe=alpaca_tf)
            min_required = bars_per_year + vol_avg_bars + 5
            if len(bars) < min_required:
                skipped.append(symbol)
                print(f"  {symbol}: SKIP (only {len(bars)} bars, need {min_required})")
                continue
            stock_bars_map[symbol] = bars
            stock_date_maps[symbol] = {b['timestamp'][:10]: idx for idx, b in enumerate(bars)}
            print(f"  {symbol}: {len(bars)} bars")
        except Exception as e:
            skipped.append(symbol)
            print(f"  {symbol}: SKIP ({type(e).__name__}: {e})")

    if not stock_bars_map:
        print("\nNo stock data available. Check API connection.")
        return {}

    # ── Run portfolio-level simulation ───────────────────────────────────
    # We iterate through SPY dates chronologically.
    # On each date, scan all symbols for entry signals.
    # Manage open positions (stops, profit takes).

    print(f"\nRunning portfolio simulation...")

    starting_equity = 100_000.0
    equity = starting_equity
    peak_equity = equity
    max_dd = 0.0

    open_positions: list[dict] = []  # list of active position dicts
    all_trades: list[dict] = []
    cooldown_until: dict[str, int] = {}  # symbol → SPY bar index when cooldown expires

    # Track equity curve for drawdown
    equity_curve: list[float] = [equity]

    # Start scanning from bar bars_per_year onward (need lookback for 52w metrics)
    start_bar = max(bars_per_year, vol_avg_bars + 5, 20)

    for spy_i in range(start_bar, len(spy_bars) - 1):
        spy_date = spy_bars[spy_i]['timestamp'][:10]
        next_spy_date = spy_bars[spy_i + 1]['timestamp'][:10]

        # Compute SPY correction score for this date
        corr_score = compute_spy_correction_score(spy_bars, spy_i, bars_per_year)

        # ── MANAGE EXISTING POSITIONS ────────────────────────────────────
        positions_to_close = []
        for pos_idx, pos in enumerate(open_positions):
            symbol = pos['symbol']
            sector = pos['sector']

            # Find this date in the stock's bars
            stock_dm = stock_date_maps.get(symbol, {})
            si = stock_dm.get(spy_date)
            si_next = stock_dm.get(next_spy_date)

            if si is None or si_next is None:
                continue  # stock doesn't have data for this date

            bars = stock_bars_map[symbol]
            bar = bars[si]
            next_bar = bars[si_next]

            entry = pos['entry_price']
            pnl_pct = (bar['close'] - entry) / entry if entry > 0 else 0

            atr = compute_atr(bars[max(0, si - vol_avg_bars):si + 1])

            exited = False
            exit_reason = None
            exit_price = next_bar['open']

            # Stop loss: 25% floor OR 3×ATR below entry, whichever is tighter
            stop_25pct = entry * 0.75
            stop_3atr  = entry - (3.0 * atr) if atr > 0 else entry * 0.75
            stop_price = max(stop_25pct, stop_3atr)  # tighter = higher price

            if bar['close'] <= stop_price:
                exit_reason = 'stop_loss'
                exited = True

            # Profit take: 50%+
            elif pnl_pct >= 0.50:
                exit_reason = 'profit_take_50pct'
                exited = True

            if exited:
                raw_exit = exit_price
                exit_price = apply_slippage(raw_exit, 'sell', slippage)
                pnl_final = (exit_price - entry) / entry if entry > 0 else 0

                # Return capital to equity
                position_value = pos['position_usd'] * (1.0 + pnl_final)
                equity += position_value

                trade = {
                    'symbol':          symbol,
                    'sector':          sector,
                    'entry_price':     round(entry, 4),
                    'exit_price':      round(exit_price, 4),
                    'entry_date':      pos['entry_date'],
                    'exit_date':       next_spy_date,
                    'pnl_pct':         round(pnl_final * 100, 2),
                    'pnl_usd':         round(position_value - pos['position_usd'], 2),
                    'exit_reason':     exit_reason,
                    'hold_days':       spy_i - pos['entry_spy_idx'],
                    'conviction_score': round(pos['conviction_score'], 3),
                    'conviction_tier': pos['conviction_tier'],
                    'correction_score': pos['correction_score'],
                    'position_pct':    round(pos['position_pct'] * 100, 1),
                    'regime':          regime_map.get(pos['entry_date'], 'unknown'),
                }
                all_trades.append(trade)
                positions_to_close.append(pos_idx)

                # Set cooldown on stop-outs
                if exit_reason == 'stop_loss':
                    cooldown_until[symbol] = spy_i + cooldown_bars

        # Remove closed positions (reverse order to preserve indices)
        for idx in sorted(positions_to_close, reverse=True):
            open_positions.pop(idx)

        # Update equity curve (mark-to-market open positions)
        mtm_equity = equity
        for pos in open_positions:
            symbol = pos['symbol']
            stock_dm = stock_date_maps.get(symbol, {})
            si = stock_dm.get(spy_date)
            if si is not None:
                current_price = stock_bars_map[symbol][si]['close']
                pos_pnl = (current_price - pos['entry_price']) / pos['entry_price']
                mtm_equity += pos['position_usd'] * (1.0 + pos_pnl)
            else:
                mtm_equity += pos['position_usd']  # assume flat if no data

        if mtm_equity > peak_equity:
            peak_equity = mtm_equity
        dd = (peak_equity - mtm_equity) / peak_equity * 100.0
        if dd > max_dd:
            max_dd = dd

        equity_curve.append(mtm_equity)

        # ── ENTRY SCAN ───────────────────────────────────────────────────
        # Only enter if: correction_score > 40 AND room for more positions
        if corr_score < 40:
            continue
        if len(open_positions) >= MAX_CONCURRENT:
            continue

        # Portfolio drawdown circuit breaker: -25%
        if mtm_equity < starting_equity * 0.75:
            continue

        # Scan all symbols for entry signals
        candidates = []
        for symbol in sorted(stock_bars_map.keys()):
            # Skip if already holding
            if any(p['symbol'] == symbol for p in open_positions):
                continue

            # Skip if in cooldown
            if cooldown_until.get(symbol, 0) > spy_i:
                continue

            stock_dm = stock_date_maps.get(symbol, {})
            si = stock_dm.get(spy_date)
            si_next = stock_dm.get(next_spy_date)
            if si is None or si_next is None:
                continue

            bars = stock_bars_map[symbol]
            if si < bars_per_year:
                continue

            price = bars[si]['close']
            sector = TICKER_TO_SECTOR.get(symbol, 'unknown')
            sector_etf = SECTOR_ETFS.get(sector, '')

            # Sector momentum
            etf_dm = etf_date_maps.get(sector_etf, {})
            etf_i = etf_dm.get(spy_date)
            if etf_i is not None and etf_i >= 20 and etf_bars_map.get(sector_etf):
                sect_mom = compute_sector_momentum(etf_bars_map[sector_etf], etf_i, lookback=20)
            else:
                sect_mom = 0.0

            # Volume acceleration
            vol_accel = compute_volume_accel(bars, si, vol_avg_bars)

            # Price depression
            price_dep = compute_price_depression(bars, si, bars_per_year)

            # Conviction scoring
            conv_score, tier = score_golden_conviction(
                corr_score, sect_mom, vol_accel, price_dep, price
            )

            # Price gate
            if not price_passes(price, conv_score):
                continue

            # Must be at least exploratory conviction
            if tier == 'pass':
                continue

            # Require: sector shows momentum (>0%) AND volume surge (>1.5x) AND price depressed (<1.5x from low)
            if sect_mom <= 0.0:
                continue
            if vol_accel < 1.5:
                continue
            if price_dep > 1.5:
                continue

            candidates.append({
                'symbol': symbol,
                'sector': sector,
                'price': price,
                'conviction_score': conv_score,
                'tier': tier,
                'correction_score': corr_score,
                'sector_momentum': sect_mom,
                'volume_accel': vol_accel,
                'price_depression': price_dep,
                'si_next': si_next,
            })

        # Sort by conviction score descending, take up to available slots
        candidates.sort(key=lambda c: c['conviction_score'], reverse=True)
        slots = MAX_CONCURRENT - len(open_positions)

        for cand in candidates[:slots]:
            symbol = cand['symbol']
            tier = cand['tier']
            pos_pct = position_size_pct(tier)

            # Calculate available equity (cash not in positions)
            position_usd = equity * pos_pct
            if position_usd <= 0 or equity <= 0:
                continue

            next_bar = stock_bars_map[symbol][cand['si_next']]
            raw_entry = next_bar['open']
            if raw_entry <= 0:
                continue

            entry_price = apply_slippage(raw_entry, 'buy', slippage)

            # Deduct from available equity
            equity -= position_usd

            open_positions.append({
                'symbol': symbol,
                'sector': cand['sector'],
                'entry_price': entry_price,
                'entry_date': next_spy_date,
                'entry_spy_idx': spy_i + 1,
                'position_usd': position_usd,
                'position_pct': pos_pct,
                'conviction_score': cand['conviction_score'],
                'conviction_tier': tier,
                'correction_score': cand['correction_score'],
            })

    # ── Close remaining open positions at end ────────────────────────────
    final_date = spy_bars[-1]['timestamp'][:10]
    for pos in open_positions:
        symbol = pos['symbol']
        stock_dm = stock_date_maps.get(symbol, {})
        # Find latest available bar
        bars = stock_bars_map.get(symbol, [])
        if not bars:
            continue
        last_bar = bars[-1]
        raw_exit = last_bar['close']
        exit_price = apply_slippage(raw_exit, 'sell', slippage)
        entry = pos['entry_price']
        pnl_final = (exit_price - entry) / entry if entry > 0 else 0
        position_value = pos['position_usd'] * (1.0 + pnl_final)
        equity += position_value

        all_trades.append({
            'symbol':          symbol,
            'sector':          pos['sector'],
            'entry_price':     round(entry, 4),
            'exit_price':      round(exit_price, 4),
            'entry_date':      pos['entry_date'],
            'exit_date':       last_bar['timestamp'][:10],
            'pnl_pct':         round(pnl_final * 100, 2),
            'pnl_usd':         round(position_value - pos['position_usd'], 2),
            'exit_reason':     'end_of_period',
            'hold_days':       len(spy_bars) - pos['entry_spy_idx'],
            'conviction_score': round(pos['conviction_score'], 3),
            'conviction_tier': pos['conviction_tier'],
            'correction_score': pos['correction_score'],
            'position_pct':    round(pos['position_pct'] * 100, 1),
            'regime':          regime_map.get(pos['entry_date'], 'unknown'),
        })
    open_positions = []

    if not all_trades:
        print("\nNo trades generated. SPY may not have had correction windows in this period.")
        return {}

    # ── Compute stats ────────────────────────────────────────────────────
    stats_all = compute_golden_stats(all_trades, starting_equity, max_dd)
    in_sample  = [t for t in all_trades if t['entry_date'] < split_date]
    out_sample = [t for t in all_trades if t['entry_date'] >= split_date]
    stats_in  = compute_golden_stats(in_sample, starting_equity, 0)
    stats_out = compute_golden_stats(out_sample, starting_equity, 0)

    # ── Regime breakdown ─────────────────────────────────────────────────
    regime_breakdown: dict[str, dict] = {}
    for reg in ('bull', 'bear', 'neutral', 'unknown'):
        rt = [t for t in all_trades if t['regime'] == reg]
        if rt:
            regime_breakdown[reg] = {
                'trades':    len(rt),
                'win_rate':  round(len([t for t in rt if t['pnl_pct'] > 0]) / len(rt) * 100, 1),
                'avg_pnl':   round(float(np.mean([t['pnl_pct'] for t in rt])), 2),
            }

    # ── Sector breakdown ─────────────────────────────────────────────────
    sector_stats: dict[str, dict] = {}
    for sector in GOLDEN_UNIVERSE:
        st = [t for t in all_trades if t['sector'] == sector]
        if st:
            sw = [t for t in st if t['pnl_pct'] > 0]
            sector_stats[sector] = {
                'trades':   len(st),
                'win_rate': round(len(sw) / len(st) * 100, 1),
                'avg_pnl':  round(float(np.mean([t['pnl_pct'] for t in st])), 2),
            }

    # ── Conviction tier breakdown ────────────────────────────────────────
    tier_stats: dict[str, dict] = {}
    for tier in ('high', 'medium', 'exploratory'):
        tt = [t for t in all_trades if t['conviction_tier'] == tier]
        if tt:
            tw = [t for t in tt if t['pnl_pct'] > 0]
            tier_stats[tier] = {
                'trades':   len(tt),
                'win_rate': round(len(tw) / len(tt) * 100, 1),
                'avg_pnl':  round(float(np.mean([t['pnl_pct'] for t in tt])), 2),
                'avg_position_pct': round(float(np.mean([t['position_pct'] for t in tt])), 1),
            }

    # ── Exit reason breakdown ────────────────────────────────────────────
    exit_counts: dict[str, int] = {}
    for t in all_trades:
        exit_counts[t['exit_reason']] = exit_counts.get(t['exit_reason'], 0) + 1

    # ── Top trades ───────────────────────────────────────────────────────
    top5 = sorted(all_trades, key=lambda t: t['pnl_pct'], reverse=True)[:5]

    # ── Format report ────────────────────────────────────────────────────
    final_equity = equity
    for pos in open_positions:
        final_equity += pos['position_usd']  # shouldn't be any, but safety
    total_return = (final_equity - starting_equity) / starting_equity * 100

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
            f"  Sharpe:        {s['sharpe']:.2f}",
            f"  Avg Hold:      {s['avg_hold_days']:.1f} bars",
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
        '  GOLDEN STRATEGY PROXY BACKTEST RESULTS',
        '=' * 60,
        f"  Timeframe:     {timeframe} bars",
        f"  Lookback:      {lookback} calendar days (~{len(spy_bars)} {timeframe} bars)",
        f"  Split date:    {split_date}",
        f"  Slippage:      {slippage*100:.2f}% per fill",
        f"  Max positions: {MAX_CONCURRENT}",
        f"  SPY return:    {spy_return:+.1f}% over same period",
        '',
        '⚠  SURVIVORSHIP BIAS: universe is current survivors only.',
        '⚠  PROXY SCORING: Uses sector ETF momentum / volume / price depression',
        '   instead of actual 13F/ARK holdings data.',
    ]

    output_lines.append(fmt_stats('ALL TRADES', stats_all))
    output_lines.append(fmt_stats(f'IN-SAMPLE  (before {split_date})', stats_in))
    output_lines.append(fmt_stats(f'OUT-OF-SAMPLE  (from {split_date})', stats_out))

    # Criteria check (on out-of-sample if available, else all)
    check_stats = stats_out if stats_out['total_trades'] > 0 else stats_all
    output_lines.append('\n' + format_criteria_block(check_stats))

    output_lines.append('\nBY SECTOR:')
    for sec, ss in sector_stats.items():
        output_lines.append(
            f"  {sec:25s}: {ss['trades']:3d} trades | {ss['win_rate']:.0f}% win | avg {ss['avg_pnl']:+.1f}%"
        )

    output_lines.append('\nBY CONVICTION TIER:')
    for tier, ts in tier_stats.items():
        output_lines.append(
            f"  {tier:15s}: {ts['trades']:3d} trades | {ts['win_rate']:.0f}% win | "
            f"avg {ts['avg_pnl']:+.1f}% | avg position {ts['avg_position_pct']:.0f}%"
        )

    output_lines.append('\nBY REGIME (at entry):')
    for reg, rs in regime_breakdown.items():
        output_lines.append(
            f"  {reg:10s}: {rs['trades']:3d} trades | {rs['win_rate']:.0f}% win | avg {rs['avg_pnl']:+.1f}%"
        )

    output_lines.append('\nEXIT REASONS:')
    for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
        pct = count / len(all_trades) * 100
        output_lines.append(f"  {reason:25s}: {count:3d}  ({pct:.0f}%)")

    output_lines.append('\nTOP 5 TRADES:')
    for idx, t in enumerate(top5, 1):
        output_lines.append(
            f"  {idx}. {t['symbol']:6s}: {t['pnl_pct']:+.1f}%"
            f"  ({t['exit_reason']}, {t['hold_days']}d, tier={t['conviction_tier']}, "
            f"corr={t['correction_score']})"
        )

    if skipped:
        output_lines.append(f"\nSkipped ({len(skipped)}): {', '.join(skipped)}")

    output_lines.append('')
    output = '\n'.join(output_lines)
    print(output)

    # ── Save results ─────────────────────────────────────────────────────
    out_dir = os.path.dirname(__file__)

    summary = {
        'run_ts':      datetime.now(timezone.utc).isoformat(),
        'params': {
            'lookback': lookback, 'split_date': split_date,
            'slippage': slippage, 'timeframe': timeframe,
            'max_positions': MAX_CONCURRENT,
        },
        'spy_return_pct': round(spy_return, 2),
        'all':        stats_all,
        'in_sample':  stats_in,
        'out_sample': stats_out,
        'by_sector':  sector_stats,
        'by_tier':    tier_stats,
        'by_regime':  regime_breakdown,
        'exit_reasons': exit_counts,
        'success_criteria': check_golden_success(check_stats),
        'top_5_trades': top5,
        'symbols_skipped': skipped,
    }

    with open(os.path.join(out_dir, 'golden_results.json'), 'w') as f:
        json.dump({'summary': summary, 'trades': all_trades}, f, indent=2, default=str)

    with open(os.path.join(out_dir, 'golden_results_latest.txt'), 'w') as f:
        f.write(output)

    with open(os.path.join(out_dir, 'golden_trades.csv'), 'w', newline='') as f:
        if all_trades:
            writer = csv.DictWriter(f, fieldnames=all_trades[0].keys())
            writer.writeheader()
            writer.writerows(all_trades)

    print(f"Saved: golden_results.json  golden_results_latest.txt  golden_trades.csv\n")
    return summary


# ── Stats helpers ─────────────────────────────────────────────────────────────

def compute_golden_stats(trades: list[dict], starting_equity: float = 100_000,
                          max_dd_override: float = 0) -> dict:
    """Compute performance stats for Golden trades."""
    empty = {
        'total_trades': 0, 'winning_trades': 0, 'win_rate_pct': 0,
        'avg_win_pct': 0, 'avg_loss_pct': 0, 'win_loss_ratio': 0,
        'expectancy_per_trade': 0, 'profit_factor': 0,
        'total_return_pct': 0, 'final_equity': starting_equity,
        'max_drawdown_pct': 0, 'sharpe': 0,
        'avg_hold_days': 0, 'best_trade': None, 'worst_trade': None,
    }
    if not trades:
        return empty

    wins   = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]

    avg_win  = float(np.mean([t['pnl_pct'] for t in wins]))   if wins   else 0.0
    avg_loss = float(np.mean([t['pnl_pct'] for t in losses])) if losses else 0.0
    win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

    win_rate = len(wins) / len(trades)
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
    gross_wins   = sum(t['pnl_pct'] for t in wins)
    gross_losses = abs(sum(t['pnl_pct'] for t in losses)) if losses else 1.0
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float('inf')

    # Sequential equity using actual position sizing from trades
    equity = starting_equity
    peak = equity
    max_dd = 0.0
    returns: list[float] = []
    sorted_trades = sorted(trades, key=lambda x: x['entry_date'])
    for t in sorted_trades:
        pnl_usd = t.get('pnl_usd', 0)
        if pnl_usd == 0:
            # Fallback: estimate from position_pct
            pos_usd = equity * (t.get('position_pct', 5) / 100.0)
            pnl_usd = pos_usd * (t['pnl_pct'] / 100.0)
        equity += pnl_usd
        returns.append(t['pnl_pct'])
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100.0
        if dd > max_dd:
            max_dd = dd

    total_return = (equity - starting_equity) / starting_equity * 100.0
    if max_dd_override > 0:
        max_dd = max_dd_override

    if len(returns) > 1:
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252 / max(1, len(returns))))
    else:
        sharpe = 0.0

    hold_days = [t.get('hold_days', 0) for t in sorted_trades]
    avg_hold = float(np.mean(hold_days)) if hold_days else 0.0

    best  = max(sorted_trades, key=lambda t: t['pnl_pct'])
    worst = min(sorted_trades, key=lambda t: t['pnl_pct'])

    return {
        'total_trades':         len(trades),
        'winning_trades':       len(wins),
        'win_rate_pct':         round(win_rate * 100, 1),
        'avg_win_pct':          round(avg_win, 2),
        'avg_loss_pct':         round(avg_loss, 2),
        'win_loss_ratio':       round(win_loss_ratio, 2) if win_loss_ratio != float('inf') else float('inf'),
        'expectancy_per_trade': round(expectancy, 2),
        'profit_factor':        round(profit_factor, 2) if profit_factor != float('inf') else float('inf'),
        'total_return_pct':     round(total_return, 1),
        'final_equity':         round(equity, 2),
        'max_drawdown_pct':     round(max_dd, 1),
        'sharpe':               round(sharpe, 2),
        'avg_hold_days':        round(avg_hold, 1),
        'best_trade':           {'symbol': best['symbol'], 'pnl_pct': best['pnl_pct'],
                                 'sector': best['sector'], 'date': best['entry_date']},
        'worst_trade':          {'symbol': worst['symbol'], 'pnl_pct': worst['pnl_pct'],
                                 'sector': worst['sector'], 'date': worst['entry_date']},
    }


def check_golden_success(stats: dict) -> dict[str, bool]:
    """Run pre-defined criteria against a stats dict."""
    results = {}
    for key, rule in SUCCESS_CRITERIA.items():
        val = stats.get(key, 0)
        if val is None:
            val = 0
        if isinstance(val, float) and val == float('inf'):
            val = 999
        if rule['op'] == '>=':
            results[key] = val >= rule['threshold']
        elif rule['op'] == '<=':
            results[key] = val <= rule['threshold']
    return results


def format_criteria_block(stats: dict) -> str:
    """Print success criteria with pass/fail."""
    passed = check_golden_success(stats)
    lines = ['SUCCESS CRITERIA (pre-defined):']
    all_pass = True
    for key, rule in SUCCESS_CRITERIA.items():
        val = stats.get(key, 0)
        ok = passed[key]
        if not ok:
            all_pass = False
        mark = 'PASS' if ok else 'FAIL'
        lines.append(f'  [{mark}] {rule["label"]:30s}  got: {val}')
    lines.append(f'  Overall: {"ALL PASS" if all_pass else "CRITERIA NOT MET"}')
    return '\n'.join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Golden Strategy Proxy Backtester')
    parser.add_argument('--lookback', type=int, default=1260,
                        help='Calendar days to fetch (default 1260 ≈ 5 years)')
    parser.add_argument('--split', type=str, default='2024-01-01',
                        help='In-sample/out-of-sample split date YYYY-MM-DD')
    parser.add_argument('--slippage', type=float, default=0.0075,
                        help='Adverse slippage per fill (default 0.0075 = 0.75%%)')
    parser.add_argument('--timeframe', type=str, default='day',
                        choices=['5min', '10min', '20min', 'minute', 'hour', 'day', 'week', 'month'],
                        help='Bar timeframe (default: day)')
    args = parser.parse_args()
    run_golden_backtest(
        lookback=args.lookback,
        split_date=args.split,
        slippage=args.slippage,
        timeframe=args.timeframe,
    )
