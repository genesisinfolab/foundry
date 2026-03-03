"""
Alpha Scanner

Fetches and parses external content sources (YouTube, URLs, RSS feeds, raw text),
then asks Claude to extract actionable alpha: tickers, setups, catalysts, themes.

Supported source types:
  youtube  — video or live-stream URL (uses youtube-transcript-api)
  url      — any webpage (uses trafilatura for clean text extraction)
  rss      — RSS/Atom feed (parses latest entries)
  text     — raw text submitted directly from the dashboard

Never raises at the top level — all failures are logged and return None.
"""
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.alpha import AlphaSource, AlphaInsight

logger = logging.getLogger(__name__)

# How many characters of content to send Claude (last N chars for long transcripts,
# so we capture the MOST RECENT portion of a long live-stream).
_CLAUDE_CONTENT_CHARS = 14_000

_ALPHA_SYSTEM = (
    "You are a professional trading analyst and market intelligence expert. "
    "Your job is to extract clean, actionable alpha from market commentary. "
    "Be concise and specific. Only mention tickers that were meaningfully discussed, "
    "not just passing references."
)

_ALPHA_PROMPT = """\
Analyze the following market content from "{source_name}" and extract actionable alpha.

Respond in EXACTLY this format (no extra text before or after):

TICKERS: [list of {{"symbol":"XYZ","sentiment":"bullish|bearish|watching|neutral","note":"brief reason"}}]
SETUPS: [bullet list of specific chart patterns or technical setups mentioned, or "none"]
CATALYSTS: [bullet list of news events, earnings, FDA decisions, macro data mentioned, or "none"]
THEMES: [bullet list of broad sector or macro themes, or "none"]
VERDICT: [one sentence summary of the overall market tone and key takeaway]

CONTENT:
{content}
"""


# ── Content fetchers ──────────────────────────────────────────────────────────

def _extract_video_id(url: str) -> Optional[str]:
    """
    Pull the 11-char YouTube video ID from any YouTube URL format.

    Handles:
      https://www.youtube.com/watch?v=VIDEO_ID
      https://youtu.be/VIDEO_ID
      https://www.youtube.com/live/VIDEO_ID
      https://www.youtube.com/@ChannelHandle/live   ← follows HTTP redirect
      https://www.youtube.com/channel/CHANNEL_ID/live ← follows redirect
    """
    # Direct video ID patterns
    patterns = [
        r'[?&]v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'embed/([a-zA-Z0-9_-]{11})',
        r'/live/([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)

    # Channel /live URL — scrape page HTML to find the current live stream video ID
    # e.g. https://www.youtube.com/@ChannelHandle/live
    if re.search(r'youtube\.com/(@[^/]+|channel/[^/]+)/live', url):
        try:
            import httpx
            resp = httpx.get(
                url,
                timeout=15,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                cookies={"CONSENT": "YES+cb", "SOCS": "CAESEwgDEgk2MTk5NTA1MTkaAmVuIAEaBgiA_LysBg"},
            )
            # After redirect, final URL should contain the video ID
            final_url = str(resp.url)
            for p in [r'[?&]v=([a-zA-Z0-9_-]{11})', r'/live/([a-zA-Z0-9_-]{11})']:
                m = re.search(p, final_url)
                if m:
                    logger.debug(f"Channel /live redirect resolved: {url} → {final_url}")
                    return m.group(1)
            # Fallback: search response HTML for canonical video ID
            m = re.search(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', resp.text)
            if m:
                logger.debug(f"Channel /live video ID extracted from HTML: {m.group(1)}")
                return m.group(1)
        except Exception as e:
            logger.debug(f"Channel /live redirect failed for {url}: {e}")

    return None


def _scrape_youtube_metadata(vid_id: str) -> tuple[str, str]:
    """
    Fallback for live streams where captions aren't available yet.
    Scrapes the video page for title, description, and chapter headings.
    Returns (content_text, stream_title) suitable for Claude analysis.
    """
    import httpx
    resp = httpx.get(
        f"https://www.youtube.com/watch?v={vid_id}",
        timeout=15,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
        cookies={"CONSENT": "YES+cb", "SOCS": "CAESEwgDEgk2MTk5NTA1MTkaAmVuIAEaBgiA_LysBg"},
    )

    parts: list[str] = []
    stream_title = vid_id  # fallback

    # Title
    m = re.search(r'"title"\s*:\s*"([^"]{10,})"', resp.text)
    if m:
        stream_title = m.group(1)
        parts.append(f"STREAM TITLE: {stream_title}")

    # Description (first pass — simpleText)
    m = re.search(r'"description"\s*:\s*\{"simpleText"\s*:\s*"(.*?)"', resp.text, re.DOTALL)
    if m:
        desc = m.group(1).replace("\\n", "\n").replace('\\"', '"')[:1000]
        if len(desc) > 80:   # skip pure-link descriptions
            parts.append(f"\nDESCRIPTION:\n{desc}")

    # Chapters / timestamps (if any)
    chapters = re.findall(r'"chapterRenderer".*?"title"\s*:\s*\{"simpleText"\s*:\s*"([^"]+)"', resp.text)
    if chapters:
        parts.append("\nCHAPTERS / TOPICS:\n" + "\n".join(f"  • {c}" for c in chapters))

    # Pinned / top comments (optional enrichment)
    top_comments = re.findall(
        r'"contentText"\s*:\s*\{"runs"\s*:\s*\[\{"text"\s*:\s*"([^"]{20,200})"',
        resp.text
    )
    if top_comments:
        parts.append("\nTOP COMMENTS (viewer context):\n" + "\n".join(
            f"  • {c}" for c in top_comments[:5]
        ))

    if not parts:
        raise ValueError(f"Could not extract any metadata from live stream {vid_id}")

    header = "[LIVE STREAM — captions not yet available; analysis based on title/metadata]\n\n"
    return header + "\n".join(parts), stream_title


def fetch_youtube(url: str) -> tuple[str, str]:
    """
    Fetch transcript from a YouTube video or live-stream.
    Returns (transcript_text, video_id).

    For completed videos: uses youtube-transcript-api (v1.x instance API).
    For active live streams (no captions yet): falls back to page metadata scrape
    (title, description, chapters) so Claude can still extract alpha from the topic.

    For long videos (>45 min), only the last 45 minutes of transcript is used
    so that live-stream analysis focuses on the most recent commentary.
    """
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

    vid_id = _extract_video_id(url)
    if not vid_id:
        raise ValueError(f"Cannot extract video ID from URL: {url}")

    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(vid_id, languages=["en", "en-US"])
    except (NoTranscriptFound, AttributeError):
        # Fall back to any available language
        try:
            transcript_list = api.list(vid_id)
            fetched = transcript_list.find_generated_transcript(
                [t.language_code for t in transcript_list]
            ).fetch()
        except Exception:
            fetched = api.fetch(vid_id)   # last resort — let it raise naturally
    except TranscriptsDisabled:
        # Live stream in progress — captions not generated yet.
        # Scrape page metadata (title, description, chapters) as a fallback.
        logger.info(f"Live stream {vid_id}: captions not yet available — scraping metadata")
        text, stream_title = _scrape_youtube_metadata(vid_id)
        return text, stream_title

    # FetchedTranscript is iterable; each element has .start, .duration, .text
    transcript = [{"start": s.start, "text": s.text} for s in fetched]

    if not transcript:
        raise ValueError(f"Empty transcript returned for {vid_id}")

    # For long content, focus on the most recent 45 minutes (2700 seconds)
    if transcript[-1]["start"] > 2700:
        cutoff = transcript[-1]["start"] - 2700
        transcript = [t for t in transcript if t["start"] >= cutoff]

    text = " ".join(t["text"] for t in transcript)
    return text, vid_id


def fetch_url(url: str) -> str:
    """
    Fetch and extract main text content from any URL.
    Uses trafilatura for clean extraction; falls back to regex strip.
    """
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            )
            if text and len(text) > 200:
                return text
    except Exception as e:
        logger.debug(f"trafilatura failed for {url}: {e}")

    # Fallback: raw HTTP + strip HTML
    import httpx
    resp = httpx.get(
        url, timeout=20, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NewmanAlphaScanner/1.0)"}
    )
    resp.raise_for_status()
    clean = re.sub(r"<[^>]+>", " ", resp.text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:30_000]


def fetch_rss(url: str) -> str:
    """
    Fetch an RSS/Atom feed and return concatenated text of the latest 10 entries.
    """
    import feedparser
    feed = feedparser.parse(url)
    if not feed.entries:
        raise ValueError(f"No entries found in RSS feed: {url}")

    parts = []
    for entry in feed.entries[:10]:
        title   = entry.get("title", "")
        summary = entry.get("summary", "") or entry.get("description", "")
        # Strip HTML from summary
        summary = re.sub(r"<[^>]+>", " ", summary)
        summary = re.sub(r"\s+", " ", summary).strip()
        if title or summary:
            parts.append(f"HEADLINE: {title}\n{summary}")

    return "\n\n---\n\n".join(parts)


# ── Claude analysis ───────────────────────────────────────────────────────────

def analyze_with_claude(source_name: str, content: str) -> dict:
    """
    Send content to Claude for alpha extraction.
    Returns a dict: {tickers, setups, catalysts, themes, verdict, sentiment}.
    Raises on API failure — callers should handle.
    """
    import anthropic
    from app.config import get_settings

    api_key = get_settings().anthropic_api_key or None
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    # Use the LAST N chars so live-stream analysis is always current
    trimmed = content[-_CLAUDE_CONTENT_CHARS:] if len(content) > _CLAUDE_CONTENT_CHARS else content

    prompt = _ALPHA_PROMPT.format(source_name=source_name, content=trimmed)

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=_ALPHA_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_response(msg.content[0].text.strip())


def _parse_response(text: str) -> dict:
    """Parse Claude's structured TICKERS/SETUPS/CATALYSTS/THEMES/VERDICT response."""
    result: dict = {
        "tickers":   [],
        "setups":    [],
        "catalysts": [],
        "themes":    [],
        "verdict":   "",
        "sentiment": "neutral",
    }

    # TICKERS: [JSON array]
    m = re.search(r"TICKERS:\s*(\[.*?\])", text, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(1))
            result["tickers"] = parsed if isinstance(parsed, list) else []
        except Exception:
            syms = re.findall(r'"symbol"\s*:\s*"([A-Z]{1,5})"', m.group(1))
            result["tickers"] = [{"symbol": s, "sentiment": "mentioned", "note": ""} for s in syms]

    # SETUPS / CATALYSTS / THEMES: bullet lists
    for key in ("SETUPS", "CATALYSTS", "THEMES"):
        m = re.search(rf"{key}:\s*\[(.*?)\]", text, re.DOTALL)
        if m:
            raw = m.group(1).strip()
            if raw.lower() not in ("none", ""):
                items = [i.strip().strip('"').strip() for i in raw.split(",") if i.strip().strip('"')]
                # Handle newline-separated bullet lists inside the brackets
                if len(items) <= 1 and "\n" in raw:
                    items = [l.strip().lstrip("-•* ") for l in raw.splitlines() if l.strip()]
                result[key.lower()] = [i for i in items if i and i.lower() != "none"]

    # VERDICT: rest of line
    m = re.search(r"VERDICT:\s*(.+)", text)
    if m:
        result["verdict"] = m.group(1).strip()

    # Derive overall sentiment from ticker sentiments
    tickers = result["tickers"]
    bullish = sum(1 for t in tickers if "bull" in str(t.get("sentiment", "")).lower())
    bearish = sum(1 for t in tickers if "bear" in str(t.get("sentiment", "")).lower())
    if bullish > 0 and bearish == 0:
        result["sentiment"] = "bullish"
    elif bearish > 0 and bullish == 0:
        result["sentiment"] = "bearish"
    elif bullish > 0 or bearish > 0:
        result["sentiment"] = "mixed"

    return result


# ── Main entry points ─────────────────────────────────────────────────────────

def scan_source(source: AlphaSource, db: Session) -> Optional[AlphaInsight]:
    """
    Fetch and analyze one registered AlphaSource.
    Persists a new AlphaInsight row and returns it, or None on failure.
    """
    try:
        video_title = None

        if source.source_type == "youtube":
            content, video_title = fetch_youtube(source.url)
        elif source.source_type == "url":
            content = fetch_url(source.url)
        elif source.source_type == "rss":
            content = fetch_rss(source.url)
        else:
            logger.warning(f"scan_source called on text-type source {source.name} — use scan_text instead")
            return None

        if not content or len(content) < 100:
            logger.warning(f"Alpha source '{source.name}': content too short ({len(content) if content else 0} chars)")
            return None

        # Attempt Claude analysis; degrade gracefully if API key not set
        try:
            result     = analyze_with_claude(source.name, content)
            analysis   = _format_analysis(result)
            tickers_j  = json.dumps(result["tickers"])
            sentiment  = result.get("sentiment", "neutral")
        except Exception as e:
            logger.warning(f"Claude analysis unavailable for '{source.name}': {e}")
            analysis  = f"Claude analysis unavailable ({type(e).__name__}). Add ANTHROPIC_API_KEY to .env."
            tickers_j = "[]"
            sentiment = "neutral"

        insight = AlphaInsight(
            source_id       = source.id,
            content_preview = content[:500],
            tickers         = tickers_j,
            analysis        = analysis,
            sentiment       = sentiment,
            raw_length      = len(content),
            video_title     = video_title,
        )
        db.add(insight)
        source.last_fetched = datetime.now(timezone.utc)
        db.commit()
        db.refresh(insight)
        logger.info(f"Alpha scan complete: '{source.name}' → {len(result.get('tickers', []))} tickers, sentiment={sentiment}")

        # ── Chat approval / auto-approve flow ────────────────────────────────
        # Extract bullish tickers and propose them to the Newman strategy.
        bullish = [
            t for t in result.get("tickers", [])
            if "bull" in str(t.get("sentiment", "")).lower()
        ] if result else []
        if bullish:
            _propose_alpha_to_chat(source, bullish, result.get("verdict", ""), db)

        return insight

    except Exception as e:
        logger.error(f"Alpha scan failed for '{source.name}': {e}")
        return None


def _propose_alpha_to_chat(
    source: AlphaSource,
    bullish_tickers: list[dict],
    verdict: str,
    db: Session,
) -> None:
    """
    Post a chat message proposing bullish tickers from an alpha scan.

    If the source has auto_approve=True, adds them to the watchlist immediately
    and posts a confirmation. Otherwise posts a YES/NO/ALWAYS prompt for the user.

    Pending proposals are stored in the module-level dict so the chat route
    can resolve them when the user replies.
    """
    try:
        syms = [t["symbol"] if isinstance(t, dict) else t for t in bullish_tickers]
        notes = {
            (t["symbol"] if isinstance(t, dict) else t): t.get("note", "")
            for t in bullish_tickers
            if isinstance(t, dict)
        }

        if source.auto_approve:
            _add_to_watchlist(syms, source.name, notes, db)
            msg = (
                f"**Alpha Auto-approved** from *{source.name}*\n\n"
                f"Added to Newman watchlist for breakout monitoring: "
                f"{', '.join(f'**${s}**' for s in syms)}\n\n"
                f"_{verdict}_\n\n"
                f"_(Auto-approved because you set this source to always allow. "
                f"Reply `REVOKE {source.id}` to turn off auto-approval.)_"
            )
            _post_chat(msg, db)
        else:
            # Store pending proposal so chat route can resolve YES/NO/ALWAYS
            proposal_key = f"alpha_{source.id}_{datetime.now(timezone.utc).strftime('%H%M%S')}"
            _pending_proposals[proposal_key] = {
                "source_id":   source.id,
                "source_name": source.name,
                "symbols":     syms,
                "notes":       notes,
                "verdict":     verdict,
                "created_at":  datetime.now(timezone.utc),
            }
            ticker_lines = "\n".join(
                f"  • **${s}**" + (f" — {notes[s]}" if notes.get(s) else "")
                for s in syms
            )
            msg = (
                f"**Alpha Intel** from *{source.name}*\n\n"
                f"Claude found {len(syms)} bullish ticker(s):\n{ticker_lines}\n\n"
                f"_{verdict}_\n\n"
                f"Should I add these to the Newman watchlist for breakout monitoring?\n"
                f"Reply **YES** to add  |  **NO** to skip  |  **ALWAYS** to auto-approve this source\n"
                f"_(Proposal ID: `{proposal_key}`)_"
            )
            _post_chat(msg, db)

    except Exception as e:
        logger.warning(f"_propose_alpha_to_chat failed: {e}")


# Module-level pending proposals dict  {proposal_key: {source_id, symbols, notes, verdict}}
_pending_proposals: dict[str, dict] = {}


def resolve_alpha_proposal(reply: str, db: Session) -> Optional[str]:
    """
    Called by the chat route when the user replies to an alpha proposal.
    Returns a response string to post back, or None if this wasn't an alpha reply.
    """
    reply_upper = reply.strip().upper()

    # REVOKE source_id — turn off auto-approve
    if reply_upper.startswith("REVOKE "):
        try:
            source_id = int(reply_upper.split()[1])
            source = db.query(AlphaSource).filter(AlphaSource.id == source_id).first()
            if source:
                source.auto_approve = False
                db.commit()
                return f"Auto-approval revoked for **{source.name}**. You'll be asked before adding tickers."
        except Exception:
            pass
        return None

    # Prune proposals older than 24 hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    stale = [k for k, v in _pending_proposals.items() if v.get("created_at", cutoff) < cutoff]
    for k in stale:
        _pending_proposals.pop(k)

    # Check if reply is YES / NO / ALWAYS (matches any pending proposal)
    if reply_upper not in ("YES", "NO", "ALWAYS"):
        return None
    if not _pending_proposals:
        return None

    # Take the most recent pending proposal
    proposal_key = sorted(_pending_proposals.keys())[-1]
    proposal = _pending_proposals.pop(proposal_key)
    syms  = proposal["symbols"]
    notes = proposal["notes"]

    if reply_upper == "NO":
        return f"Skipped — {', '.join(f'${s}' for s in syms)} not added to watchlist."

    # YES or ALWAYS — add to watchlist
    _add_to_watchlist(syms, proposal["source_name"], notes, db)
    response = (
        f"Added **{', '.join(f'${s}' for s in syms)}** to Newman watchlist "
        f"for trendline breakout monitoring."
    )

    if reply_upper == "ALWAYS":
        try:
            source = db.query(AlphaSource).filter(AlphaSource.id == proposal["source_id"]).first()
            if source:
                source.auto_approve = True
                db.commit()
                response += f"\n\nAuto-approval enabled for **{proposal['source_name']}** — future scans will add tickers immediately."
        except Exception as e:
            logger.warning(f"Failed to set auto_approve: {e}")

    return response


def _add_to_watchlist(symbols: list[str], source_name: str, notes: dict, db: Session) -> None:
    """Add symbols to the WatchlistItem table if not already present."""
    from app.models.watchlist import WatchlistItem
    from app.integrations.alpaca_client import AlpacaClient
    alpaca = AlpacaClient()
    added = []
    for sym in symbols:
        # Validate symbol is a tradeable US equity on Alpaca
        try:
            assets = alpaca.search_assets(sym)
            if not assets:
                logger.warning(f"Alpha Intel: skipping {sym} — not found on Alpaca")
                continue
        except Exception as e:
            logger.warning(f"Alpha Intel: skipping {sym} — validation error: {e}")
            continue
        existing = db.query(WatchlistItem).filter(WatchlistItem.symbol == sym).first()
        if not existing:
            item = WatchlistItem(
                symbol         = sym,
                active         = True,
                company_name   = notes.get(sym, ""),
                catalyst_notes = f"Added by Alpha Intel ({source_name})",
            )
            db.add(item)
            added.append(sym)
        elif not existing.active:
            existing.active = True
            added.append(f"{sym}(re-activated)")
    if added:
        db.commit()
        logger.info(f"Alpha Intel added to watchlist: {added}")


def _post_chat(message: str, db: Session) -> None:
    """Post a message to the chat log as the bot (broadcasts via SSE)."""
    try:
        from app.services.chat_log import append as chat_append
        chat_append(role="assistant", content=message, source="alpha_intel")
    except Exception as e:
        logger.warning(f"_post_chat failed: {e}")


def scan_text(source_name: str, content: str, db: Session) -> Optional[AlphaInsight]:
    """
    Analyze a block of raw text (manual paste or programmatic submission).
    Creates or reuses a __manual__ source row.
    """
    try:
        manual = db.query(AlphaSource).filter(AlphaSource.source_type == "text").first()
        if not manual:
            manual = AlphaSource(name="Manual Input", source_type="text", url="", active=False)
            db.add(manual)
            db.flush()

        try:
            result    = analyze_with_claude(source_name or "Manual Input", content)
            analysis  = _format_analysis(result)
            tickers_j = json.dumps(result["tickers"])
            sentiment = result.get("sentiment", "neutral")
        except Exception as e:
            logger.warning(f"Claude analysis unavailable for manual input: {e}")
            analysis  = f"Claude analysis unavailable ({type(e).__name__}). Add ANTHROPIC_API_KEY to .env."
            tickers_j = "[]"
            sentiment = "neutral"

        insight = AlphaInsight(
            source_id       = manual.id,
            content_preview = content[:500],
            tickers         = tickers_j,
            analysis        = analysis,
            sentiment       = sentiment,
            raw_length      = len(content),
            video_title     = source_name or "Manual Input",
        )
        db.add(insight)
        manual.last_fetched = datetime.now(timezone.utc)
        db.commit()
        db.refresh(insight)
        return insight

    except Exception as e:
        logger.error(f"scan_text failed: {e}")
        return None


def _format_analysis(result: dict) -> str:
    """Format parsed Claude result into a human-readable string for storage."""
    lines = []
    if result.get("verdict"):
        lines.append(f"VERDICT: {result['verdict']}")
    if result.get("setups"):
        lines.append("\nSETUPS:")
        lines.extend(f"  • {s}" for s in result["setups"])
    if result.get("catalysts"):
        lines.append("\nCATALYSTS:")
        lines.extend(f"  • {c}" for c in result["catalysts"])
    if result.get("themes"):
        lines.append("\nTHEMES:")
        lines.extend(f"  • {t}" for t in result["themes"])
    return "\n".join(lines).strip()
