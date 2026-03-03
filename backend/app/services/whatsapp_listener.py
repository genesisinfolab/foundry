"""
WhatsApp Incoming Message Listener

Polls the local wacli SQLite DB for new incoming messages from the
owner's phone number, then routes them through the same command
handler as the webhook endpoint.

Architecture:
  - wacli sync --once runs every POLL_INTERVAL seconds to pull new
    messages from WhatsApp into the local DB, then exits (releases lock)
  - We read the DB directly (read-only) to find new incoming messages
  - Commands are processed via handle_command()
  - Responses sent via notifier._send() (spawns its own wacli process)
"""
import logging
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

WACLI_DB   = str(Path.home() / ".wacli" / "wacli.db")
POLL_INTERVAL = 20   # seconds between sync cycles


class WhatsAppListener:
    def __init__(self, owner_jid: str):
        self.owner_jid = owner_jid          # e.g. "18136193622@s.whatsapp.net"
        self._last_rowid = self._max_rowid()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _max_rowid(self) -> int:
        try:
            conn = sqlite3.connect(f"file:{WACLI_DB}?mode=ro", uri=True, timeout=5)
            row  = conn.execute("SELECT COALESCE(MAX(rowid),0) FROM messages").fetchone()
            conn.close()
            return row[0]
        except Exception:
            return 0

    def _new_messages(self) -> list[tuple[int, str]]:
        """Return (rowid, text) for new incoming messages from owner."""
        try:
            conn = sqlite3.connect(f"file:{WACLI_DB}?mode=ro", uri=True, timeout=5)
            rows = conn.execute(
                "SELECT rowid, text FROM messages "
                "WHERE from_me=0 AND chat_jid=? AND rowid>? AND text IS NOT NULL "
                "ORDER BY rowid ASC",
                (self.owner_jid, self._last_rowid),
            ).fetchall()
            conn.close()
            return rows
        except Exception as e:
            logger.warning(f"wacli DB read failed: {e}")
            return []

    # ── Sync ──────────────────────────────────────────────────────────────────

    def _sync_once(self):
        """Pull new messages from WhatsApp into local DB, then release lock."""
        try:
            subprocess.run(
                ["wacli", "sync", "--once", "--idle-exit", "6s"],
                timeout=25,
                capture_output=True,
            )
        except subprocess.TimeoutExpired:
            logger.warning("wacli sync --once timed out")
        except Exception as e:
            logger.warning(f"wacli sync --once failed: {e}")

    # ── Command routing ───────────────────────────────────────────────────────

    def _handle(self, text: str):
        """Process a command text exactly as the webhook would."""
        logger.info(f"WhatsApp command received: {text!r}")
        try:
            from app.services import chat_log
            chat_log.append(role="user", content=text, source="whatsapp")
        except Exception:
            pass

        try:
            from app.database import SessionLocal
            from app.routes.whatsapp import handle_command
            db = SessionLocal()
            try:
                handle_command(text, db)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"WhatsApp command handling failed: {e}")

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self):
        logger.info("WhatsApp listener started (polling every %ds)", POLL_INTERVAL)
        while not self._stop.is_set():
            try:
                self._sync_once()
                for rowid, text in self._new_messages():
                    self._last_rowid = max(self._last_rowid, rowid)
                    if text and text.strip():
                        self._handle(text.strip())
            except Exception as e:
                logger.error(f"WhatsApp listener loop error: {e}")
            self._stop.wait(POLL_INTERVAL)
        logger.info("WhatsApp listener stopped.")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="whatsapp-listener"
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
