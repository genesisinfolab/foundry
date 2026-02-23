# Newman Trading System — Build Spec

## Overview
Rebuild the Jeffrey Newman penny-stock/sector-breakout trading system from scratch. Clean architecture, fully wired end-to-end, with a dashboard UI and Alpaca paper trading.

## Architecture

### Backend: Python (FastAPI)
- `backend/` directory
- FastAPI REST API
- SQLite database (via SQLAlchemy)
- Background task scheduler (APScheduler) for scanning
- All API integrations as modular services

### Frontend: Next.js + Tailwind + shadcn/ui
- `frontend/` directory
- Dashboard showing: active themes, watchlist, positions, P&L, alerts
- Real-time updates via polling (websockets later)
- Charts for price/volume (lightweight-charts or recharts)

### Shared
- `.env` at project root for all API keys
- `docker-compose.yml` for easy deployment later

## Newman Strategy Pipeline (THE CORE)

The system must execute these steps IN ORDER:

### Step 1: Theme Detection
Scan multiple sources to identify emerging sectors/themes:
- **News**: Finnhub news API — scan for keywords ("approval", "legalization", "breakthrough", etc.)
- **Social**: Twitter API (search for trending tickers/sectors), Reddit (r/pennystocks, r/wallstreetbets)
- **ETF Performance**: Track specialized ETFs (MJ, ARKQ, PRNT, TAN, etc.) for unusual price/volume via Alpaca market data
- **Sector Rotation**: Alpha Vantage sector performance endpoint
- Score each theme by: news_mentions * 0.4 + social_buzz * 0.3 + etf_performance * 0.3

### Step 2: Watchlist Building
For each "hot" theme detected:
- Find all stocks in that sector via:
  - ETF holdings (scrape or API)
  - Alpha Vantage symbol search
  - Finnhub industry peers
- Track potential catalysts: earnings dates, FDA dates, legislative dates
- Store in DB with metadata: theme, date_added, catalyst_info

### Step 3: Share Structure Filter ("Clean Structure Check")
For each watchlist stock, pull fundamentals:
- Finnhub: shares outstanding, float, market cap, daily volume
- Alpha Vantage: company overview (float, shares outstanding)
- **Filter criteria**:
  - Float < 200M shares
  - Price > $0.50
  - Average daily volume > some minimum (e.g., 100k)
  - No obvious dilution red flags
- Remove stocks that fail → "clean watchlist"

### Step 4: Breakout Detection & Volume Monitoring
For clean watchlist stocks, monitor via Alpaca market data:
- Volume surge: current volume > 2-3x 20-day average
- Price breakout: closing above downtrend line or multi-week consolidation range
- Accumulation detection: large block trades, bid-side volume
- When triggered → generate ALERT

### Step 5: Shotgun Entry
When breakout alert fires:
- Place small starter position ($1,000-$5,000 equivalent based on account size)
- Use Alpaca paper trading API
- Track entry price, volume at entry, theme association

### Step 6: Pyramiding
If position shows strength (up 3%+ on continued volume):
- Scale in: Tier 1 (2% of portfolio), Tier 2 (5%), Tier 3 (10%)
- Max single position: 35% of portfolio
- Max theme exposure: 60% of portfolio

### Step 7: Risk Management & Exits
- Stop loss: -0.5% from entry (tight!)
- Profit taking: Scale out at +15%, +30%, +45%
- Theme exit: If media saturation detected (too much buzz = top signal)
- Hard limits: Max 4 pyramid levels per position

## API Integrations

### Alpaca (Paper Trading + Market Data)
- Key: PKG3E5X4GUWBFV40HK9H
- Secret: HALu9DC2kw5ubayd1jytYsEdJ72xmDEaOWHzkeLY
- Endpoint: https://paper-api.alpaca.markets/v2
- Use `alpaca-py` SDK
- For: order placement, position tracking, historical bars, real-time quotes

### Finnhub
- Key: ctvde39r01qh15ov68c0ctvde39r01qh15ov68cg
- For: news, company fundamentals, industry peers, earnings calendar

### Twitter
- Bearer: AAAAAAAAAAAAAAAAAAAAAJ7AxgEAAAAACIntu6E0GfAcBwz5vX%2BKQAZha9Q%3DBQNTQ0Hr92toNJFlyjefpMYCpC0Y7BaI4y6tR9bR8awmEp1NYe
- Full OAuth keys also available
- For: trending stock mentions, sector sentiment

### Reddit (via PRAW)
- Client ID: wkf4tP7Dd3Cy0zXG6JRpIQ
- Client Secret: DD5IYi7PWUNMTqX7TuHpiQ5lSHCHKQ
- For: r/pennystocks, r/wallstreetbets sentiment scanning

### Alpha Vantage
- Key: ZBPRZ7LS337926JG
- For: sector performance, company overviews, symbol search
- NOTE: Free tier = 25 requests/day, use caching aggressively

### Perigon News
- Key: 83aa4b20-69dc-42fa-a992-801572cb917b
- For: Additional news aggregation

### Seeking Alpha (RapidAPI)
- Key: 9c50155207msh80a7f7f7c046d18p16f1f3jsn0ca044d42d22
- For: Analysis, ratings

## Dashboard UI Requirements

### Main Dashboard
- **Theme Scanner**: Shows detected themes with strength scores, trending direction
- **Watchlist**: Current watchlist with theme tags, volume status, breakout proximity
- **Positions**: Open positions with P&L, entry price, pyramid level, theme
- **Alerts Feed**: Real-time alerts for breakouts, volume surges, stop-loss triggers
- **Account Overview**: Portfolio value, cash, buying power, daily P&L

### Theme Detail View
- All stocks in a theme
- Theme strength over time (chart)
- News/social mentions feeding the theme

### Stock Detail View
- Price chart with volume bars
- Key fundamentals (float, market cap, avg volume)
- Entry/exit signals marked on chart
- Position history if traded

## File Structure
```
newman-trading/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── config.py            # Settings from .env
│   │   ├── database.py          # SQLAlchemy setup
│   │   ├── models/              # DB models
│   │   │   ├── theme.py
│   │   │   ├── watchlist.py
│   │   │   ├── position.py
│   │   │   └── alert.py
│   │   ├── services/            # Business logic
│   │   │   ├── theme_detector.py
│   │   │   ├── watchlist_builder.py
│   │   │   ├── structure_checker.py
│   │   │   ├── breakout_scanner.py
│   │   │   ├── trade_executor.py
│   │   │   └── risk_manager.py
│   │   ├── integrations/        # External APIs
│   │   │   ├── alpaca_client.py
│   │   │   ├── finnhub_client.py
│   │   │   ├── twitter_client.py
│   │   │   ├── reddit_client.py
│   │   │   ├── alpha_vantage_client.py
│   │   │   └── perigon_client.py
│   │   ├── routes/              # API endpoints
│   │   │   ├── themes.py
│   │   │   ├── watchlist.py
│   │   │   ├── positions.py
│   │   │   └── alerts.py
│   │   └── scheduler.py         # Background scan jobs
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   ├── package.json
│   └── Dockerfile
├── .env
├── docker-compose.yml
└── README.md
```

## Priority Order
1. Backend: Config + DB models + Alpaca client (get paper trading working)
2. Backend: Theme detector + watchlist builder (wire the pipeline)
3. Backend: Breakout scanner + trade executor + risk manager
4. Backend: API routes exposing everything
5. Frontend: Dashboard with all views
6. Integration: End-to-end test with real theme detection → paper trade

## Reference
- Existing (messy) code at: /Users/agent/.openclaw/workspace/alpaca-trading/
- Use as reference for Newman strategy logic, NOT for architecture
- Key files to reference: app/strategies/newman_theme_strategy.py, app/services/volume_analyzer.py
