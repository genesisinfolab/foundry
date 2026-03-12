# Foundry — Project Instructions

## What This Is
Jeffrey Newman penny-stock/sector-breakout trading system.
Semi-autonomous. Paper trading via Alpaca. Dashboard at foundry.markets.

## Stack
- **Backend**: FastAPI + SQLAlchemy + APScheduler — `backend/`
- **Frontend**: Next.js 15 + Tailwind + shadcn/ui + Recharts — `frontend/`
- **DB**: SQLite locally (`newman_trading.db`), persisted volume in prod (`/data/foundry.db`)
- **Auth**: Supabase (`@supabase/ssr`, `@supabase/supabase-js`)

## Deployment
| Target | Where | How |
|---|---|---|
| Backend | Fly.io (`foundry-backend.fly.dev`) | `fly deploy` from `backend/` |
| Frontend | Vercel | `vercel --prod` from `frontend/` |
| DB migrations | Alembic | `alembic upgrade head` |

**Known issue**: `wacli` is not installed on Fly.io. All WhatsApp notifications silently fail in production. Do not attempt to send WhatsApp alerts from the backend until this is resolved.

## Local Dev
```bash
# Backend
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8080

# Frontend
cd frontend && npm run dev
```

## Key Files
- `backend/app/main.py` — FastAPI entrypoint
- `backend/app/` — routers, services, models
- `backend/fly.toml` — Fly.io config (region: iad, port: 8080)
- `frontend/src/` — Next.js app router
- `SPEC.md` — canonical system spec (read before building anything)
- `RETROSPECTIVE.md` — Newman retro failure analysis (read before debugging)

## Newman Strategy Pipeline (order matters)
1. Theme Detection (news + social + ETF performance)
2. Watchlist Building (sector stocks per theme)
3. Share Structure Filter (float < 200M, price > $0.50, vol > 100k)
4. Breakout Detection (2-3x volume surge + price breakout)
5. Shotgun Entry ($1k-$5k starter via Alpaca paper)
6. Pyramiding (Tier 1: 2%, Tier 2: 5%, Tier 3: 10% — max 35% single position)
7. Risk Management (stop: -0.5%, profit: scale at +15/+30/+45%, max 4 pyramid levels)

## External APIs in Use
- Alpaca (paper trading + market data)
- Finnhub (news, fundamentals, peers)
- Alpha Vantage (sector performance, company overview)
- Praw/Reddit (r/pennystocks, r/wallstreetbets)
- Tweepy/Twitter (trending tickers)
- Anthropic (claude-opus-4-6 — AI analysis layer)

## Rules
- Read SPEC.md before adding any new feature.
- Read RETROSPECTIVE.md before debugging.
- Never deploy without running migrations first.
- Never hardcode API keys — all keys via `.env` at project root.
- Frontend polls backend; no WebSocket until explicitly scoped.
- Test on paper trading only. Never touch live Alpaca account.
- Needs full SDD pipeline re-run before next major build phase.
