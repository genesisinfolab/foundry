"""Newman Trading System — FastAPI Application"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.scheduler import create_scheduler
from app.routes import themes, watchlist, positions, alerts, pipeline

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
    scheduler.start()
    logger.info("Scheduler started. Scanning will run during market hours.")
    yield
    # Shutdown
    scheduler.shutdown()
    logger.info("Newman Trading System stopped.")


app = FastAPI(
    title="Newman Trading System",
    description="Jeffrey Newman's sector-breakout trading strategy, automated.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(themes.router)
app.include_router(watchlist.router)
app.include_router(positions.router)
app.include_router(alerts.router)
app.include_router(pipeline.router)


@app.get("/")
def root():
    from app.services import newman_persona
    return {
        "name": "Newman Trading System",
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
def account():
    from app.integrations.alpaca_client import AlpacaClient
    client = AlpacaClient()
    return client.get_account()
