"""Alpaca Trading & Market Data Client"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetAssetsRequest
from alpaca.trading.enums import OrderSide, TimeInForce, AssetClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame

from app.config import get_settings

logger = logging.getLogger(__name__)


class AlpacaClient:
    def __init__(self):
        s = get_settings()
        self.trading = TradingClient(s.alpaca_api_key_id, s.alpaca_api_secret_key, paper=s.alpaca_paper)
        self.data = StockHistoricalDataClient(s.alpaca_api_key_id, s.alpaca_api_secret_key)

    # ── Account ──────────────────────────────────────────────
    def get_account(self) -> dict:
        acct = self.trading.get_account()
        return {
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
            "portfolio_value": float(acct.portfolio_value),
            "daily_pnl": float(acct.equity) - float(acct.last_equity),
        }

    # ── Positions ────────────────────────────────────────────
    def get_positions(self) -> list[dict]:
        positions = self.trading.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pnl": float(p.unrealized_pl),
                "unrealized_pnl_pct": float(p.unrealized_plpc),
            }
            for p in positions
        ]

    # ── Orders ───────────────────────────────────────────────
    def place_market_order(self, symbol: str, qty: float, side: str = "buy") -> dict:
        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = self.trading.submit_order(req)
        logger.info(f"Order placed: {side} {qty} {symbol} → {order.id}")
        return {
            "order_id": str(order.id),
            "symbol": order.symbol,
            "qty": str(order.qty),
            "side": order.side.value,
            "status": order.status.value,
        }

    def close_position(self, symbol: str) -> dict:
        order = self.trading.close_position(symbol)
        logger.info(f"Position closed: {symbol} → {order.id}")
        return {"order_id": str(order.id), "symbol": symbol, "status": "closing"}

    # ── Market Data ──────────────────────────────────────────
    def get_bars(self, symbol: str, days: int = 30, timeframe: TimeFrame = TimeFrame.Day) -> list[dict]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=timeframe, start=start, end=end)
        bars = self.data.get_stock_bars(req)
        return [
            {
                "timestamp": bar.timestamp.isoformat(),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
                "vwap": float(bar.vwap) if bar.vwap else None,
            }
            for bar in bars[symbol]
        ]

    def get_bars_batch(self, symbols: list[str], days: int = 60, timeframe: TimeFrame = TimeFrame.Day) -> dict[str, list[dict]]:
        """Fetch bars for multiple symbols in a single API call (much faster than looping)."""
        if not symbols:
            return {}
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=timeframe, start=start, end=end)
        all_bars = self.data.get_stock_bars(req)
        result = {}
        for sym in symbols:
            try:
                result[sym] = [
                    {
                        "timestamp": bar.timestamp.isoformat(),
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                        "vwap": float(bar.vwap) if bar.vwap else None,
                    }
                    for bar in all_bars[sym]
                ]
            except (KeyError, Exception):
                result[sym] = []
        return result

    def get_latest_quote(self, symbol: str) -> dict:
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = self.data.get_stock_latest_quote(req)
        q = quotes[symbol]
        return {
            "symbol": symbol,
            "bid": float(q.bid_price),
            "ask": float(q.ask_price),
            "bid_size": int(q.bid_size),
            "ask_size": int(q.ask_size),
        }

    def get_snapshots_batch(self, symbols: list[str]) -> dict[str, dict]:
        """
        Fetch latest snapshot for multiple symbols in one call.
        Returns {symbol: {price, prev_close, change_pct, change_usd}}.
        """
        if not symbols:
            return {}
        req = StockSnapshotRequest(symbol_or_symbols=symbols)
        raw = self.data.get_stock_snapshot(req)
        result = {}
        for sym in symbols:
            try:
                snap = raw[sym]
                current = (
                    float(snap.latest_trade.price)
                    if snap.latest_trade
                    else (float(snap.daily_bar.close) if snap.daily_bar else 0.0)
                )
                prev = float(snap.previous_daily_bar.close) if snap.previous_daily_bar else current
                change_pct = ((current - prev) / prev * 100) if prev > 0 else 0.0
                result[sym] = {
                    "symbol":     sym,
                    "price":      round(current, 2),
                    "prev_close": round(prev, 2),
                    "change_pct": round(change_pct, 2),
                    "change_usd": round(current - prev, 2),
                }
            except (KeyError, Exception):
                result[sym] = {"symbol": sym, "price": 0.0, "prev_close": 0.0,
                               "change_pct": 0.0, "change_usd": 0.0}
        return result

    def get_snapshot(self, symbol: str) -> dict:
        req = StockSnapshotRequest(symbol_or_symbols=symbol)
        snapshots = self.data.get_stock_snapshot(req)
        snap = snapshots[symbol]
        return {
            "symbol": symbol,
            "latest_trade_price": float(snap.latest_trade.price) if snap.latest_trade else None,
            "daily_bar": {
                "open": float(snap.daily_bar.open),
                "high": float(snap.daily_bar.high),
                "low": float(snap.daily_bar.low),
                "close": float(snap.daily_bar.close),
                "volume": int(snap.daily_bar.volume),
            } if snap.daily_bar else None,
            "prev_daily_bar": {
                "close": float(snap.previous_daily_bar.close),
                "volume": int(snap.previous_daily_bar.volume),
            } if snap.previous_daily_bar else None,
        }

    def get_avg_volume(self, symbol: str, days: int = 20) -> float:
        bars = self.get_bars(symbol, days=days)
        if not bars:
            return 0.0
        return sum(b["volume"] for b in bars) / len(bars)

    # ── Portfolio History ─────────────────────────────────────
    def get_portfolio_history(self, days: int = 30) -> list[dict]:
        """
        Fetch daily portfolio history from Alpaca via direct REST call.
        Returns list of {date: str, equity_pct: float} sorted by date.
        equity_pct is cumulative return % from account's starting value.
        Uses direct HTTP to avoid SDK version compatibility issues.
        """
        import json
        import urllib.request
        from datetime import datetime, timezone

        s = get_settings()
        base_url = "https://paper-api.alpaca.markets" if s.alpaca_paper else "https://api.alpaca.markets"
        url = f"{base_url}/v2/account/portfolio/history?timeframe=1D&period={days}D&extended_hours=false"
        try:
            req = urllib.request.Request(url, headers={
                "APCA-API-KEY-ID": s.alpaca_api_key_id,
                "APCA-API-SECRET-KEY": s.alpaca_api_secret_key,
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())

            timestamps = data.get("timestamp") or []
            equities = data.get("equity") or []
            base = float(data.get("base_value") or 0)

            if not timestamps or base <= 0:
                return []

            seen: dict[str, float] = {}
            for ts, eq in zip(timestamps, equities):
                if eq is None:
                    continue
                date_str = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
                seen[date_str] = round((float(eq) - base) / base * 100, 4)

            return [{"date": d, "equity_pct": p} for d, p in sorted(seen.items())]
        except Exception as e:
            logger.warning(f"Alpaca portfolio history failed: {e}")
            return []

    # ── Asset Search ─────────────────────────────────────────
    def search_assets(self, status: str = "active") -> list[dict]:
        req = GetAssetsRequest(asset_class=AssetClass.US_EQUITY, status=status)
        assets = self.trading.get_all_assets(req)
        return [
            {"symbol": a.symbol, "name": a.name, "exchange": a.exchange, "tradable": a.tradable}
            for a in assets if a.tradable
        ]
