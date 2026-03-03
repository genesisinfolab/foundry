"""Foundry — FastAPI Application"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.services.auth import require_supabase_token
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import init_db
import app.models.alpha  # ensure alpha tables are created by init_db
from app.scheduler import create_scheduler
from app.routes import themes, watchlist, positions, alerts, pipeline
from app.routes import dashboard, whatsapp, chat
from app.routes import alpha
from app.routes import public

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = create_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Newman Trading System...")
    init_db()

    # Pre-seed agent tracker so the dashboard shows all agents immediately
    from app.services import agent_tracker
    for _agent_name in [
        "theme_detector", "watchlist_builder", "structure_checker",
        "breakout_scanner", "risk_manager", "trade_executor", "health_check",
    ]:
        with agent_tracker._lock:
            agent_tracker._agents[_agent_name] = {
                "status":      "idle",
                "detail":      "Waiting for next scheduled scan",
                "last_run":    None,
                "last_action": None,
                "error":       None,
            }

    # Start WhatsApp listener (polls wacli DB for incoming commands)
    from app.services.whatsapp_listener import WhatsAppListener
    from app.services.notifier import _to_jid
    _wa_number = settings.whatsapp_number
    _wa_listener = None
    if _wa_number:
        _wa_listener = WhatsAppListener(owner_jid=_to_jid(_wa_number))
        _wa_listener.start()
        logger.info("WhatsApp listener started.")
    else:
        logger.warning("WHATSAPP_NUMBER not set — incoming WhatsApp commands disabled.")

    scheduler.start()
    logger.info("Scheduler started. Scanning will run during market hours.")
    yield
    # Shutdown
    if _wa_listener:
        _wa_listener.stop()
    scheduler.shutdown()
    logger.info("Newman Trading System stopped.")


app = FastAPI(
    title="Foundry",
    description="Sector-breakout trading — systematically identified, automatically executed.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "https://*.loca.lt", "https://*.vercel.app",
        "https://foundry.markets", "https://www.foundry.markets",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (dashboard HTML, future assets)
_static = Path(__file__).resolve().parent / "static"
_static.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static)), name="static")

# Register routes
app.include_router(themes.router)
app.include_router(watchlist.router)
app.include_router(positions.router)
app.include_router(alerts.router)
app.include_router(pipeline.router)
app.include_router(dashboard.router)   # /dashboard/  + /dashboard/events
app.include_router(whatsapp.router)    # /api/whatsapp/webhook
app.include_router(chat.router)        # /api/chat/history + /api/chat/send
app.include_router(alpha.router)       # /api/alpha/sources + insights + scan
app.include_router(public.router)      # /api/public/stats


@app.get("/")
def root():
    from app.services import newman_persona
    return {
        "name": "Foundry",
        "version": "1.0.0",
        "status": "running",
        "persona": newman_persona.PERSONA_NAME,
    }


@app.get("/api/persona")
def persona():
    """Return the active trading persona and its operating parameters."""
    from app.services import newman_persona
    return newman_persona.describe()


@app.get("/api/account")
def account(_token=Depends(require_supabase_token)):
    from app.integrations.alpaca_client import AlpacaClient
    client = AlpacaClient()
    return client.get_account()
