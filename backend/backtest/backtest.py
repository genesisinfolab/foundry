#!/usr/bin/env python3
"""Newman Strategy Backtester — runs against Alpaca historical data"""
import sys, os, argparse, json, csv, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

from datetime import datetime, timezone
import numpy as np

logging.basicConfig(level=logging.WARNING)

SECTOR_UNIVERSE = {
    'cannabis': ['MSOS', 'TLRY', 'CGC', 'ACB', 'CRON'],
    'clean_energy': ['ENPH', 'SEDG', 'FSLR', 'RUN', 'ARRY'],
    'biotech': ['MRNA', 'BNTX', 'NVAX', 'CRSP', 'BEAM'],
    'semiconductors': ['NVDA', 'AMD', 'SMCI', 'MRVL', 'ON'],
    'ev': ['RIVN', 'LCID', 'GOEV', 'NKLA', 'SOLO'],
    'ai_software': ['SOUN', 'BBAI', 'AITX'],
    'uranium': ['UEC', 'UUUU', 'DNN', 'CCJ', 'NXE'],
    'space': ['RKLB', 'ASTR', 'SPCE', 'ASTS'],
}

def compute_atr(bars, period=14):
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]['high'], bars[i]['low'], bars[i-1]['close']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < period:
        return trs[-1] if trs else 0
    return float(np.mean(trs[-period:]))

def backtest_symbol(symbol, sector, bars):
    """Simulate Newman strategy on a list of daily bars. Returns list of trade dicts."""
    if len(bars) < 25:
        return []
    trades = []
    position = None  # dict: {entry_price, entry_date, qty, stop, pyramid_level, profit_taken}

    closes = [b['close'] for b in bars]
    opens = [b['open'] for b in bars]
    highs = [b['high'] for b in bars]
    lows = [b['low'] for b in bars]
    volumes = [b['volume'] for b in bars]
    dates = [b['timestamp'] for b in bars]

    for i in range(20, len(bars) - 1):
        avg_vol_20 = float(np.mean(volumes[i-20:i]))
        high_20 = max(closes[i-20:i])
        atr = compute_atr(bars[max(0, i-14):i+1])

        if position is None:
            # ENTRY check
            if (volumes[i] > 2.5 * avg_vol_20 and
                closes[i] >= high_20 * 0.98 and
                opens[i+1] > 0):
                entry = opens[i+1]
                position = {
                    'entry_price': entry,
                    'entry_date': dates[i+1],
                    'qty': 100,
                    'stop': entry - 1.5 * atr,
                    'pyramid_level': 0,
                    'profit_taken': 0,
                }
        else:
            entry = position['entry_price']
            pnl_pct = (closes[i] - entry) / entry if entry > 0 else 0

            exited = False
            exit_reason = None
            exit_price = opens[i+1]

            # Stop loss
            if closes[i] <= position['stop']:
                exit_reason = 'stop_loss'
                exited = True
            # Profit tier 3 (45%+)
            elif pnl_pct >= 0.45:
                exit_reason = 'profit_t3'
                exited = True
            # Profit tier 2 (30%+)
            elif pnl_pct >= 0.30 and position['profit_taken'] < 2:
                position['qty'] = int(position['qty'] * 0.67)
                position['profit_taken'] = 2
            # Profit tier 1 (15%+)
            elif pnl_pct >= 0.15 and position['profit_taken'] < 1:
                position['qty'] = int(position['qty'] * 0.67)
                position['profit_taken'] = 1
            # Pyramid (3%+ gain + volume surge)
            elif (pnl_pct >= 0.03 and
                  position['pyramid_level'] < 2 and
                  volumes[i] > 2.0 * avg_vol_20):
                position['qty'] = int(position['qty'] * 1.5)
                position['pyramid_level'] += 1

            if exited:
                pnl_final = (exit_price - entry) / entry
                trades.append({
                    'symbol': symbol,
                    'sector': sector,
                    'entry_price': round(entry, 4),
                    'exit_price': round(exit_price, 4),
                    'entry_date': str(dates[position.get('entry_idx', i)])[:10],
                    'exit_date': str(dates[i+1])[:10],
                    'pnl_pct': round(pnl_final * 100, 2),
                    'exit_reason': exit_reason,
                    'hold_days': i - max(0, i - 50),
                    'pyramid_levels': position['pyramid_level'],
                })
                position = None

    # Close any open position at end
    if position is not None:
        entry = position['entry_price']
        exit_price = closes[-1]
        pnl_final = (exit_price - entry) / entry
        trades.append({
            'symbol': symbol,
            'sector': sector,
            'entry_price': round(entry, 4),
            'exit_price': round(exit_price, 4),
            'entry_date': str(dates[0])[:10],
            'exit_date': str(dates[-1])[:10],
            'pnl_pct': round(pnl_final * 100, 2),
            'exit_reason': 'end_of_period',
            'hold_days': len(bars),
            'pyramid_levels': position['pyramid_level'],
        })
    return trades

def run_backtest(lookback=252):
    from app.integrations.alpaca_client import AlpacaClient
    client = AlpacaClient()

    all_trades = []
    skipped = []

    for sector, symbols in SECTOR_UNIVERSE.items():
        print(f"\nScanning {sector}...")
        for symbol in symbols:
            try:
                bars = client.get_bars(symbol, days=lookback)
                if len(bars) < 25:
                    skipped.append(symbol)
                    continue
                trades = backtest_symbol(symbol, sector, bars)
                all_trades.extend(trades)
                print(f"  {symbol}: {len(trades)} trades from {len(bars)} bars")
            except Exception as e:
                skipped.append(symbol)
                print(f"  {symbol}: SKIP ({type(e).__name__})")

    if not all_trades:
        print("\nNo trades found. Check API connection.")
        return

    # Compute stats
    wins = [t for t in all_trades if t['pnl_pct'] > 0]
    losses = [t for t in all_trades if t['pnl_pct'] <= 0]
    win_rate = len(wins) / len(all_trades) * 100 if all_trades else 0
    avg_win = float(np.mean([t['pnl_pct'] for t in wins])) if wins else 0
    avg_loss = float(np.mean([t['pnl_pct'] for t in losses])) if losses else 0
    best = max(all_trades, key=lambda t: t['pnl_pct'])
    worst = min(all_trades, key=lambda t: t['pnl_pct'])

    # Simulate equity curve ($100k, equal position sizing)
    equity = 100000.0
    pos_size = equity / max(len(all_trades), 1) * 5  # 5% per trade
    max_eq = equity
    max_dd = 0.0
    for t in sorted(all_trades, key=lambda x: x['entry_date']):
        equity += pos_size * t['pnl_pct'] / 100
        if equity > max_eq:
            max_eq = equity
        dd = (max_eq - equity) / max_eq * 100
        if dd > max_dd:
            max_dd = dd
    total_return = (equity - 100000) / 100000 * 100

    # By sector
    sector_stats = {}
    for sector in SECTOR_UNIVERSE.keys():
        st = [t for t in all_trades if t['sector'] == sector]
        if st:
            sw = [t for t in st if t['pnl_pct'] > 0]
            sector_stats[sector] = {
                'trades': len(st),
                'win_rate': len(sw) / len(st) * 100,
                'avg_pnl': float(np.mean([t['pnl_pct'] for t in st])),
            }

    # Top 5 trades
    top5 = sorted(all_trades, key=lambda t: t['pnl_pct'], reverse=True)[:5]

    summary = {
        'period_days': lookback,
        'total_symbols_tested': sum(len(v) for v in SECTOR_UNIVERSE.values()),
        'symbols_skipped': len(skipped),
        'total_trades': len(all_trades),
        'winning_trades': len(wins),
        'win_rate_pct': round(win_rate, 1),
        'avg_win_pct': round(avg_win, 2),
        'avg_loss_pct': round(avg_loss, 2),
        'best_trade': f"{best['symbol']} +{best['pnl_pct']:.1f}%",
        'worst_trade': f"{worst['symbol']} {worst['pnl_pct']:.1f}%",
        'total_return_pct': round(total_return, 1),
        'max_drawdown_pct': round(max_dd, 1),
        'final_equity': round(equity, 2),
        'by_sector': sector_stats,
        'top_5_trades': top5,
    }

    output = f"""
===== NEWMAN STRATEGY BACKTEST RESULTS =====
Period: {lookback} trading days lookback
Symbols tested: {summary['total_symbols_tested']} ({len(skipped)} skipped/unavailable)
Total Trades: {summary['total_trades']}
Winning Trades: {summary['winning_trades']} ({summary['win_rate_pct']:.1f}%)
Average Win: +{summary['avg_win_pct']:.1f}%
Average Loss: {summary['avg_loss_pct']:.1f}%
Best Trade: {summary['best_trade']}
Worst Trade: {summary['worst_trade']}
Total Return: {'+' if total_return > 0 else ''}{summary['total_return_pct']:.1f}% (on $100k → ${equity:,.0f})
Max Drawdown: -{summary['max_drawdown_pct']:.1f}%

BY SECTOR:
"""
    for sec, ss in sector_stats.items():
        output += f"  {sec:20s}: {ss['trades']:3d} trades | {ss['win_rate']:.0f}% win | avg {ss['avg_pnl']:+.1f}%\n"

    output += "\nTOP 5 TRADES:\n"
    for i, t in enumerate(top5, 1):
        output += f"  {i}. {t['symbol']:6s}: +{t['pnl_pct']:.1f}% ({t['exit_reason']}, {t['hold_days']}d)\n"

    output += f"\nSkipped symbols: {', '.join(skipped)}\n"

    print(output)

    # Save files
    os.makedirs(os.path.dirname(__file__), exist_ok=True)

    with open(os.path.join(os.path.dirname(__file__), 'results.json'), 'w') as f:
        json.dump({'summary': summary, 'trades': all_trades}, f, indent=2, default=str)

    with open(os.path.join(os.path.dirname(__file__), 'results_latest.txt'), 'w') as f:
        f.write(output)

    with open(os.path.join(os.path.dirname(__file__), 'trades.csv'), 'w', newline='') as f:
        if all_trades:
            writer = csv.DictWriter(f, fieldnames=all_trades[0].keys())
            writer.writeheader()
            writer.writerows(all_trades)

    print(f"\nSaved: results.json, results_latest.txt, trades.csv")
    return summary

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--lookback', type=int, default=252)
    args = parser.parse_args()
    run_backtest(args.lookback)
