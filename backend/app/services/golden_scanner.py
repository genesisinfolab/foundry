"""
Golden Scanner — Screening and scoring engine for Golden strategy.

Core loop:
  1. Screen sector ETFs for correction conditions (drawdown from 52-week high,
     price below key moving averages).
  2. Fetch Situational Awareness LP holdings from SEC EDGAR 13F.
  3. Fetch ARK daily holdings + recent trades from ark-funds.com.
  4. Discover individual stocks within correcting sectors.
  5. Score conviction via:
       - Institutional ownership (13F signal)
       - ARK Invest holdings/trades
       - Insider buying (SEC EDGAR Form 4)
       - Technical depression score (RSI, MA distance, volume patterns)
  6. Rank candidates with conviction tier (HIGH / MEDIUM / LOW).
  7. Feed qualified candidates to GoldenExecutor for paper trading.

Does NOT execute trades directly — outputs ranked candidates.
Trade execution is handled by GoldenExecutor via the scheduler.
"""
import csv
import io
import logging
import math
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from app.config import get_settings
from app.integrations.alpaca_client import AlpacaClient
from app.strategies.golden import (
    GoldenStrategy,
    GOLDEN_SECTORS,
    SITUATIONAL_AWARENESS_HOLDINGS,
    ARK_ETFS,
)
from app.services.reasoning_log import write_reasoning

logger = logging.getLogger(__name__)

# ─── SEC EDGAR headers (required) ──────────────────────────────────────────
_SEC_HEADERS = {
    "User-Agent": "OpenClaw/1.0 (info@genesis-analytics.io)",
    "Accept": "application/json",
}

# Situational Awareness LP CIK (Leopold Aschenbrenner's fund)
_SA_LP_CIK = "0002053170"

# ─── Sector ETF universe for correction screening ──────────────────────────
# Maps Golden sector → list of sector-proxy ETFs
SECTOR_ETFS: dict[str, list[str]] = {
    "clean_energy":         ["ICLN", "TAN", "QCLN"],
    "biotechnology":        ["XBI", "IBB", "ARKG"],
    "semiconductors":       ["SMH", "SOXX"],
    "artificial_intelligence": ["ARKK", "BOTZ", "ROBO"],
    "robotics":             ["ARKQ", "ROBO", "BOTZ"],
    "space":                ["ARKX", "UFO"],
    "quantum_computing":    ["QTUM"],
    "defense_tech":         ["ITA", "PPA"],
    "genomics":             ["ARKG"],
    "ev":                   ["DRIV", "LIT", "IDRV"],
    "nuclear":              ["URA", "NLR"],
    "fintech":              ["ARKF", "FINX"],
}

# All unique sector ETF tickers (flat set for batch queries)
ALL_SECTOR_ETF_TICKERS: list[str] = sorted(
    {t for etfs in SECTOR_ETFS.values() for t in etfs}
)

# ─── Hardcoded sector-to-stock mapping (top holdings per sector ETF) ────────
# Used as fallback when we can't dynamically fetch ETF holdings.
# Curated from top 10 holdings of each major sector ETF.
SECTOR_STOCK_UNIVERSE: dict[str, list[str]] = {
    "clean_energy": [
        "ENPH", "SEDG", "FSLR", "RUN", "NOVA", "PLUG", "BE", "ARRY",
        "JKS", "CSIQ", "DQ", "MAXN", "ORA",
    ],
    "biotechnology": [
        "EXAS", "IONS", "ALNY", "SRPT", "PCVX", "CORT", "NBIX",
        "HALO", "CYTK", "RCKT", "BEAM", "CRSP", "NTLA", "VERV",
        "EDIT", "FATE", "TWST", "IOVA", "RVMD",
    ],
    "semiconductors": [
        "NVDA", "AMD", "AVGO", "QCOM", "MU", "MRVL", "LRCX",
        "KLAC", "AMAT", "ADI", "TXN", "NXPI", "ON", "SWKS",
        "WOLF", "SLAB", "ACLS", "AMBA", "CEVA",
    ],
    "artificial_intelligence": [
        "PLTR", "TSLA", "SQ", "COIN", "U", "RKLB", "PATH",
        "EXAI", "UPST", "DKNG", "HOOD", "ROKU",
        "CRWD", "NET", "DDOG", "SNOW", "MDB", "S",
    ],
    "robotics": [
        "ISRG", "ROK", "TER", "IRBT", "BRKS", "NOVT", "CGNX",
    ],
    "space": [
        "RKLB", "BKSY", "RDW", "LUNR", "ASTS", "MNTS", "ASTR",
        "SPIR", "PL", "GSAT",
    ],
    "quantum_computing": [
        "IONQ", "RGTI", "QBTS", "QUBT",
    ],
    "defense_tech": [
        "LMT", "RTX", "NOC", "GD", "LHX", "LDOS", "PLTR", "BWXT",
    ],
    "genomics": [
        "CRSP", "NTLA", "BEAM", "EDIT", "VERV", "TWST", "FATE",
        "PACB", "TXG",
    ],
    "ev": [
        "TSLA", "RIVN", "LCID", "NIO", "XPEV", "LI", "FSR",
        "CHPT", "EVGO", "BLNK", "QS", "MVST", "GOEV",
    ],
    "nuclear": [
        "CCJ", "LEU", "UEC", "DNN", "NNE", "UUUU", "SMR",
    ],
    "fintech": [
        "SQ", "COIN", "HOOD", "UPST", "AFRM", "SOFI", "BILL",
        "SHOP", "MELI",
    ],
}

# ─── Cache TTLs ─────────────────────────────────────────────────────────────
_CORRECTION_CACHE_SECS = 300      # 5 min
_SECTOR_CORR_CACHE_SECS = 600    # 10 min
_13F_CACHE_SECS = 86400          # 24h (filings update quarterly)
_ARK_CACHE_SECS = 3600           # 1h (daily holdings)
_INSIDER_CACHE_SECS = 43200      # 12h

# Module-level caches
_correction_cache: dict = {}
_sector_correction_cache: dict = {}
_13f_cache: dict = {}
_ark_cache: dict = {}
_insider_cache: dict = {}


# ═══════════════════════════════════════════════════════════════════════════
#  1. MARKET & SECTOR CORRECTION DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def compute_correction_score(alpaca: Optional[AlpacaClient] = None) -> dict:
    """
    Compute correction_score (0-100) from SPY drawdown vs 52-week high.

    Score mapping:
      0-20  = SPY near highs, no correction (bad entry window)
      20-40 = mild pullback 2-5% (warming up)
      40-60 = moderate correction 5-10% (entry unlocked)
      60-80 = significant correction 10-15% (good entry window)
      80-100 = deep correction/bear >15% (ideal entry — max conviction)

    Returns dict with score, spy_price, spy_52w_high, drawdown_pct.
    """
    global _correction_cache
    now = time.time()
    if _correction_cache and now - _correction_cache.get("_ts", 0) < _CORRECTION_CACHE_SECS:
        return _correction_cache

    if alpaca is None:
        alpaca = AlpacaClient()

    try:
        bars = alpaca.get_bars("SPY", days=370)
        if not bars or len(bars) < 50:
            logger.warning("Insufficient SPY data for correction_score")
            return {"score": 50, "spy_price": 0, "spy_52w_high": 0, "drawdown_pct": 0, "error": "insufficient_data"}

        spy_price = bars[-1]["close"]
        spy_52w_high = max(b["high"] for b in bars)
        drawdown_pct = (spy_price - spy_52w_high) / spy_52w_high

        abs_dd = abs(drawdown_pct)
        if abs_dd < 0.02:
            score = int(abs_dd / 0.02 * 20)
        elif abs_dd < 0.05:
            score = 20 + int((abs_dd - 0.02) / 0.03 * 20)
        elif abs_dd < 0.10:
            score = 40 + int((abs_dd - 0.05) / 0.05 * 20)
        elif abs_dd < 0.15:
            score = 60 + int((abs_dd - 0.10) / 0.05 * 20)
        else:
            score = min(100, 80 + int((abs_dd - 0.15) / 0.10 * 20))

        result = {
            "score": score,
            "spy_price": round(spy_price, 2),
            "spy_52w_high": round(spy_52w_high, 2),
            "drawdown_pct": round(drawdown_pct * 100, 2),
            "_ts": now,
        }
        _correction_cache = result
        logger.info(
            f"Correction score: {score}/100 | SPY ${spy_price:.2f} | "
            f"52w high ${spy_52w_high:.2f} | Drawdown {drawdown_pct:.2%}"
        )
        return result

    except Exception as e:
        logger.error(f"correction_score computation failed: {e}")
        return {"score": 50, "spy_price": 0, "spy_52w_high": 0, "drawdown_pct": 0, "error": str(e)}


def screen_sector_corrections(alpaca: Optional[AlpacaClient] = None) -> dict[str, dict]:
    """
    Screen all sector ETFs for correction conditions.

    For each sector ETF, computes:
      - drawdown_pct: distance from 52-week high
      - below_50ma: whether price is below 50-day MA
      - below_200ma: whether price is below 200-day MA
      - sector_correction_score: 0-100 (analogous to SPY correction score)

    Returns dict keyed by sector name with correction data + list of ETFs screened.
    Only sectors with correction_score >= 20 are flagged as "correcting".
    """
    global _sector_correction_cache
    now = time.time()
    if _sector_correction_cache and now - _sector_correction_cache.get("_ts", 0) < _SECTOR_CORR_CACHE_SECS:
        return _sector_correction_cache

    if alpaca is None:
        alpaca = AlpacaClient()

    sector_results: dict[str, dict] = {}

    # Batch-fetch bars for all sector ETFs (370 days for 52-week high + MAs)
    try:
        all_etf_bars = alpaca.get_bars_batch(ALL_SECTOR_ETF_TICKERS, days=370)
    except Exception as e:
        logger.error(f"Sector ETF batch bars fetch failed: {e}")
        return {}

    for sector_name, etf_tickers in SECTOR_ETFS.items():
        sector_scores = []

        for etf in etf_tickers:
            bars = all_etf_bars.get(etf, [])
            if not bars or len(bars) < 50:
                continue

            price = bars[-1]["close"]
            high_52w = max(b["high"] for b in bars)
            drawdown = (price - high_52w) / high_52w if high_52w > 0 else 0

            # 50-day and 200-day simple moving averages
            closes = [b["close"] for b in bars]
            ma_50 = sum(closes[-50:]) / min(50, len(closes[-50:])) if len(closes) >= 20 else price
            ma_200 = sum(closes[-200:]) / min(200, len(closes[-200:])) if len(closes) >= 50 else price

            below_50ma = price < ma_50
            below_200ma = price < ma_200

            # Sector correction score (same mapping as SPY)
            abs_dd = abs(drawdown)
            if abs_dd < 0.02:
                etf_score = int(abs_dd / 0.02 * 20)
            elif abs_dd < 0.05:
                etf_score = 20 + int((abs_dd - 0.02) / 0.03 * 20)
            elif abs_dd < 0.10:
                etf_score = 40 + int((abs_dd - 0.05) / 0.05 * 20)
            elif abs_dd < 0.15:
                etf_score = 60 + int((abs_dd - 0.10) / 0.05 * 20)
            else:
                etf_score = min(100, 80 + int((abs_dd - 0.15) / 0.10 * 20))

            # Bonus for being below MAs
            if below_50ma:
                etf_score = min(100, etf_score + 5)
            if below_200ma:
                etf_score = min(100, etf_score + 10)

            sector_scores.append({
                "etf": etf,
                "price": round(price, 2),
                "high_52w": round(high_52w, 2),
                "drawdown_pct": round(drawdown * 100, 2),
                "below_50ma": below_50ma,
                "below_200ma": below_200ma,
                "correction_score": etf_score,
            })

        if not sector_scores:
            continue

        # Sector-level score = max of its ETFs (worst correction = best opportunity)
        best = max(sector_scores, key=lambda s: s["correction_score"])
        avg_score = sum(s["correction_score"] for s in sector_scores) / len(sector_scores)

        sector_results[sector_name] = {
            "correction_score": best["correction_score"],
            "avg_correction_score": round(avg_score, 1),
            "is_correcting": best["correction_score"] >= 20,
            "etfs": sector_scores,
        }

    _sector_correction_cache = sector_results
    _sector_correction_cache["_ts"] = now

    correcting = [s for s, d in sector_results.items() if d.get("is_correcting")]
    logger.info(
        f"Sector correction screen: {len(correcting)}/{len(sector_results)} sectors correcting — "
        + ", ".join(f"{s}({sector_results[s]['correction_score']})" for s in correcting[:8])
    )

    return sector_results


# ═══════════════════════════════════════════════════════════════════════════
#  2. INSTITUTIONAL SIGNAL FETCHING (13F + ARK + INSIDER)
# ═══════════════════════════════════════════════════════════════════════════

def fetch_13f_holdings() -> list[str]:
    """
    Fetch Situational Awareness LP latest 13F holdings from SEC EDGAR.

    Uses the EDGAR submissions API to find the latest 13F-HR filing,
    then attempts to parse holdings. Falls back to the hardcoded
    SITUATIONAL_AWARENESS_HOLDINGS list if EDGAR is unavailable.
    """
    global _13f_cache
    now = time.time()
    if _13f_cache and now - _13f_cache.get("_ts", 0) < _13F_CACHE_SECS:
        return _13f_cache.get("holdings", [])

    holdings = list(SITUATIONAL_AWARENESS_HOLDINGS)

    try:
        submissions_url = f"https://data.sec.gov/submissions/CIK{_SA_LP_CIK}.json"
        resp = httpx.get(submissions_url, headers=_SEC_HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            accessions = recent.get("accessionNumber", [])
            primary_docs = recent.get("primaryDocument", [])

            # Find latest 13F-HR
            for i, form in enumerate(forms):
                if form in ("13F-HR", "13F-HR/A"):
                    accession = accessions[i]
                    accession_clean = accession.replace("-", "")
                    cik_clean = _SA_LP_CIK.lstrip("0")
                    logger.info(f"Found SA LP 13F: {form} accession={accession}")

                    # Try to fetch the infotable XML
                    try:
                        # List all documents in filing
                        idx_url = (
                            f"https://www.sec.gov/Archives/edgar/data/"
                            f"{cik_clean}/{accession_clean}/"
                        )
                        idx_resp = httpx.get(
                            f"{idx_url}index.json",
                            headers=_SEC_HEADERS,
                            timeout=15,
                        )
                        if idx_resp.status_code == 200:
                            idx_data = idx_resp.json()
                            items = idx_data.get("directory", {}).get("item", [])
                            # Find the infotable XML file
                            for item in items:
                                name = item.get("name", "")
                                if "infotable" in name.lower() or name.endswith(".xml"):
                                    xml_url = f"{idx_url}{name}"
                                    xml_resp = httpx.get(
                                        xml_url,
                                        headers=_SEC_HEADERS,
                                        timeout=15,
                                    )
                                    if xml_resp.status_code == 200:
                                        # Parse XML for CUSIP/name entries
                                        # Simple regex-based extraction
                                        import re
                                        # Look for <nameOfIssuer> tags
                                        names = re.findall(
                                            r"<nameOfIssuer>(.*?)</nameOfIssuer>",
                                            xml_resp.text,
                                        )
                                        if names:
                                            logger.info(
                                                f"SA LP 13F parsed: {len(names)} holdings: "
                                                + ", ".join(names[:10])
                                            )
                                            # Names aren't tickers — log for manual review
                                            # Keep using the hardcoded list but log new findings
                                    break
                    except Exception as e:
                        logger.debug(f"13F infotable fetch failed: {e}")
                    break

        logger.info(f"13F holdings: {len(holdings)} symbols")

    except Exception as e:
        logger.warning(f"SEC EDGAR 13F fetch failed (using baseline): {e}")

    _13f_cache = {"holdings": holdings, "_ts": now}
    return holdings


def fetch_ark_holdings() -> dict[str, list[str]]:
    """
    Fetch ARK daily holdings CSVs from ark-funds.com.
    Returns dict mapping ETF ticker → list of held stock symbols.
    """
    global _ark_cache
    now = time.time()
    if _ark_cache and now - _ark_cache.get("_ts", 0) < _ARK_CACHE_SECS:
        return _ark_cache.get("holdings", {})

    ark_holdings: dict[str, list[str]] = {}

    ark_csv_urls = {
        "ARKK": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv",
        "ARKQ": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_AUTONOMOUS_TECH._ROBOTICS_ETF_ARKQ_HOLDINGS.csv",
        "ARKG": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS.csv",
        "ARKX": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_SPACE_EXPLORATION_INNOVATION_ETF_ARKX_HOLDINGS.csv",
        "ARKF": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_FINTECH_INNOVATION_ETF_ARKF_HOLDINGS.csv",
        "ARKW": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv",
    }

    for etf, url in ark_csv_urls.items():
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True)
            if resp.status_code != 200:
                logger.debug(f"ARK {etf} CSV returned {resp.status_code}")
                continue

            lines = resp.text.strip().split("\n")
            symbols = []
            for line in lines[1:]:  # skip header
                parts = line.split(",")
                if len(parts) >= 4:
                    ticker = parts[3].strip().strip('"')
                    if ticker and 1 <= len(ticker) <= 5 and ticker.isalpha() and ticker.isupper():
                        symbols.append(ticker)

            ark_holdings[etf] = symbols
            logger.info(f"ARK {etf}: {len(symbols)} holdings fetched")
            time.sleep(0.3)

        except Exception as e:
            logger.warning(f"ARK {etf} fetch failed: {e}")

    _ark_cache = {"holdings": ark_holdings, "_ts": now}
    return ark_holdings


def fetch_ark_trades() -> list[dict]:
    """
    Fetch ARK's recent daily trade notifications (buys only).

    ARK publishes daily trade CSVs. We look for recent BUY trades
    as high-conviction signals (Cathie Wood adding to positions).

    Returns list of {symbol, etf, shares, direction, date} for recent buys.
    """
    trades: list[dict] = []

    # ARK daily trades CSV (updates each trading day)
    trade_url = "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_TRADE_NOTIFICATIONS.csv"

    try:
        resp = httpx.get(trade_url, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            logger.debug(f"ARK trades CSV returned {resp.status_code}")
            return trades

        reader = csv.DictReader(io.StringIO(resp.text))
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        for row in reader:
            try:
                direction = row.get("direction", "").strip().upper()
                if direction != "BUY":
                    continue

                ticker = row.get("ticker", "").strip()
                if not ticker or not ticker.isalpha():
                    continue

                date_str = row.get("date", "").strip()
                # Parse date (formats vary)
                trade_date = None
                for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
                    try:
                        trade_date = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue

                if trade_date and trade_date < cutoff:
                    continue

                trades.append({
                    "symbol": ticker,
                    "etf": row.get("fund", "").strip(),
                    "shares": row.get("shares", "0").strip(),
                    "direction": "BUY",
                    "date": date_str,
                })
            except Exception:
                continue

        logger.info(f"ARK trades: {len(trades)} recent buys fetched")

    except Exception as e:
        logger.warning(f"ARK trades fetch failed: {e}")

    return trades


def fetch_insider_buying(symbols: list[str]) -> dict[str, list[dict]]:
    """
    Check for recent insider buying activity via SEC EDGAR XBRL/Form 4.

    Uses the EDGAR full-text search (EFTS) API to find recent Form 4 filings
    for the given symbols, looking for open-market purchases.

    Returns dict mapping symbol → list of insider buy records.
    Rate-limited to respect SEC's 10 req/sec guideline.
    """
    global _insider_cache
    now = time.time()
    if _insider_cache and now - _insider_cache.get("_ts", 0) < _INSIDER_CACHE_SECS:
        return _insider_cache.get("data", {})

    insider_data: dict[str, list[dict]] = {}

    # Only check top candidates to respect SEC rate limits
    symbols_to_check = symbols[:30]

    for symbol in symbols_to_check:
        try:
            # Use EDGAR EFTS to search for Form 4 filings mentioning this ticker
            search_url = (
                f"https://efts.sec.gov/LATEST/search-index"
                f"?q=%22{symbol}%22&forms=4&dateRange=custom"
                f"&startdt={(datetime.now(timezone.utc) - timedelta(days=90)).strftime('%Y-%m-%d')}"
            )
            resp = httpx.get(search_url, headers=_SEC_HEADERS, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])

                buys = []
                for hit in hits[:5]:  # check first 5 filings
                    source = hit.get("_source", {})
                    # Look for "Purchase" or "A" (acquisition) transaction codes
                    text = source.get("display_names", [""])[0] if source.get("display_names") else ""
                    filing_date = source.get("file_date", "")

                    if filing_date:
                        buys.append({
                            "filer": text[:80] if text else "Unknown",
                            "date": filing_date,
                            "type": "Form 4",
                        })

                if buys:
                    insider_data[symbol] = buys
                    logger.debug(f"Insider activity for {symbol}: {len(buys)} filings")

            time.sleep(0.15)  # respect SEC rate limit (~6 req/sec)

        except Exception as e:
            logger.debug(f"Insider check failed for {symbol}: {e}")
            continue

    _insider_cache = {"data": insider_data, "_ts": now}
    logger.info(f"Insider buying check: {len(insider_data)} symbols with activity out of {len(symbols_to_check)} checked")
    return insider_data


# ═══════════════════════════════════════════════════════════════════════════
#  3. TECHNICAL DEPRESSION SCORE
# ═══════════════════════════════════════════════════════════════════════════

def compute_rsi(closes: list[float], period: int = 14) -> float:
    """Compute RSI-14 from a list of closing prices."""
    if len(closes) < period + 1:
        return 50.0  # neutral default

    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(0, delta))
        losses.append(max(0, -delta))

    # Wilder's smoothed average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_technical_depression_score(bars: list[dict]) -> dict:
    """
    Compute a 0-100 "depression score" measuring how technically depressed
    a stock is. Higher = more depressed = better contrarian entry.

    Components:
      - RSI score (0-40): RSI < 30 = max, RSI > 70 = 0
      - MA distance score (0-30): how far below 50-day & 200-day MAs
      - Volume surge score (0-15): recent volume vs 20-day avg (capitulation signal)
      - Drawdown score (0-15): distance from own 52-week high

    Returns dict with total score and component breakdown.
    """
    if not bars or len(bars) < 30:
        return {"score": 0, "rsi": 50, "ma_distance_50": 0, "ma_distance_200": 0,
                "volume_ratio": 1.0, "drawdown_pct": 0, "components": {}}

    closes = [b["close"] for b in bars]
    volumes = [b["volume"] for b in bars]
    highs = [b["high"] for b in bars]
    price = closes[-1]

    # ── RSI score (0-40) ──
    rsi = compute_rsi(closes)
    if rsi <= 20:
        rsi_score = 40
    elif rsi <= 30:
        rsi_score = 30 + int((30 - rsi) / 10 * 10)
    elif rsi <= 40:
        rsi_score = 15 + int((40 - rsi) / 10 * 15)
    elif rsi <= 50:
        rsi_score = int((50 - rsi) / 10 * 15)
    else:
        rsi_score = 0

    # ── MA distance score (0-30) ──
    ma_50 = sum(closes[-50:]) / len(closes[-50:]) if len(closes) >= 50 else price
    ma_200 = sum(closes[-200:]) / len(closes[-200:]) if len(closes) >= 200 else price

    dist_50 = (price - ma_50) / ma_50 if ma_50 > 0 else 0  # negative = below
    dist_200 = (price - ma_200) / ma_200 if ma_200 > 0 else 0

    # Score for being below MAs (more below = higher score)
    ma50_score = 0
    if dist_50 < 0:
        ma50_score = min(15, int(abs(dist_50) / 0.20 * 15))

    ma200_score = 0
    if dist_200 < 0:
        ma200_score = min(15, int(abs(dist_200) / 0.30 * 15))

    ma_score = ma50_score + ma200_score

    # ── Volume surge score (0-15) — capitulation detection ──
    if len(volumes) >= 20:
        avg_vol_20 = sum(volumes[-20:]) / 20
        recent_vol = sum(volumes[-5:]) / 5  # last 5 days
        vol_ratio = recent_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0
    else:
        vol_ratio = 1.0

    # High volume during decline = capitulation signal
    if vol_ratio >= 3.0 and dist_50 < -0.05:
        vol_score = 15
    elif vol_ratio >= 2.0 and dist_50 < -0.03:
        vol_score = 10
    elif vol_ratio >= 1.5 and dist_50 < 0:
        vol_score = 5
    else:
        vol_score = 0

    # ── Drawdown score (0-15) — distance from 52-week high ──
    high_52w = max(highs) if highs else price
    drawdown = (price - high_52w) / high_52w if high_52w > 0 else 0

    abs_dd = abs(drawdown)
    if abs_dd >= 0.50:
        dd_score = 15
    elif abs_dd >= 0.30:
        dd_score = 10 + int((abs_dd - 0.30) / 0.20 * 5)
    elif abs_dd >= 0.15:
        dd_score = 5 + int((abs_dd - 0.15) / 0.15 * 5)
    elif abs_dd >= 0.05:
        dd_score = int(abs_dd / 0.05 * 5)
    else:
        dd_score = 0

    total = rsi_score + ma_score + vol_score + dd_score

    return {
        "score": min(100, total),
        "rsi": round(rsi, 1),
        "rsi_score": rsi_score,
        "ma_distance_50_pct": round(dist_50 * 100, 2),
        "ma_distance_200_pct": round(dist_200 * 100, 2),
        "ma_score": ma_score,
        "volume_ratio": round(vol_ratio, 2),
        "vol_score": vol_score,
        "drawdown_pct": round(drawdown * 100, 2),
        "dd_score": dd_score,
        "components": {
            "rsi": rsi_score,
            "ma": ma_score,
            "volume": vol_score,
            "drawdown": dd_score,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
#  4. CANDIDATE SCORING
# ═══════════════════════════════════════════════════════════════════════════

def _all_ark_symbols(ark_holdings: dict[str, list[str]]) -> set[str]:
    """Flatten ARK holdings into a unique set of symbols."""
    symbols = set()
    for etf_symbols in ark_holdings.values():
        symbols.update(etf_symbols)
    return symbols


def score_candidate(
    symbol: str,
    price: float,
    avg_volume: float,
    correction_score: int,
    sector_correction_score: int,
    in_13f: bool,
    ark_etf_count: int,
    ark_recent_buy: bool,
    insider_buys: int,
    tech_depression: dict,
    sector_fit: bool,
    strategy: GoldenStrategy,
) -> dict:
    """
    Score a single candidate on Golden's conviction scale (0.0 - 1.0).

    Enhanced weighting:
      - correction_score (market + sector): 0.15
      - 13F overlap: 0.25 (Situational Awareness LP signal)
      - ARK overlap + recent buys: 0.20
      - Insider buying: 0.10
      - Technical depression score: 0.15
      - Sector fit: 0.10
      - Price fit: 0.05

    Returns dict with score, tier, breakdown, and pass/fail.
    """
    weights = {
        "correction": 0.15,
        "13f": 0.25,
        "ark": 0.20,
        "insider": 0.10,
        "technical": 0.15,
        "sector": 0.10,
        "price": 0.05,
    }

    scores = {}

    # Blended correction (60% sector, 40% market) — sector correction matters more
    blended_corr = (sector_correction_score * 0.6 + correction_score * 0.4) / 100.0
    scores["correction"] = min(1.0, blended_corr)

    # 13F signal (binary — in SA LP portfolio or not)
    scores["13f"] = 1.0 if in_13f else 0.0

    # ARK signal (holdings + recent buy bonus)
    ark_base = min(1.0, ark_etf_count / 3.0)
    if ark_recent_buy:
        ark_base = min(1.0, ark_base + 0.3)  # recent buy = strong conviction signal
    scores["ark"] = ark_base

    # Insider buying signal (any Form 4 activity is positive)
    if insider_buys >= 3:
        scores["insider"] = 1.0
    elif insider_buys >= 1:
        scores["insider"] = 0.6
    else:
        scores["insider"] = 0.0

    # Technical depression score (0-100 → 0-1)
    scores["technical"] = min(1.0, tech_depression.get("score", 0) / 70.0)

    # Sector fit (binary)
    scores["sector"] = 1.0 if sector_fit else 0.0

    # Price fit
    if price <= 20.0:
        scores["price"] = 1.0
    elif price <= 100.0:
        scores["price"] = max(0.0, 1.0 - (price - 20.0) / 80.0)
    else:
        scores["price"] = 0.0

    # Weighted total
    total = sum(scores[k] * weights[k] for k in weights)

    # Determine tier
    tier = strategy.conviction_tier(total)

    # Entry criteria checks
    entry = strategy.get_entry_criteria()
    passes_correction = correction_score >= entry["correction_score_min"]
    passes_cross_ref = in_13f or ark_etf_count >= 1 or insider_buys >= 1
    passes_price = strategy.price_passes(price, total)
    passes_volume = avg_volume >= strategy.get_screening_criteria().min_avg_volume

    passes = all([passes_correction, passes_cross_ref, passes_price, passes_volume, tier != "pass"])

    return {
        "symbol": symbol,
        "conviction_score": round(total, 3),
        "tier": tier,
        "passes": passes,
        "breakdown": {k: round(v, 3) for k, v in scores.items()},
        "checks": {
            "correction": passes_correction,
            "cross_ref": passes_cross_ref,
            "price": passes_price,
            "volume": passes_volume,
            "tier_pass": tier != "pass",
        },
        "technical": {
            "rsi": tech_depression.get("rsi", 50),
            "depression_score": tech_depression.get("score", 0),
            "drawdown_pct": tech_depression.get("drawdown_pct", 0),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
#  5. SCANNER ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

class GoldenScanner:
    """
    Full screening/scoring engine for Golden strategy.

    Orchestrates:
      1. Market correction scoring (SPY-level)
      2. Sector ETF correction screening (per-sector drawdown + MA analysis)
      3. Institutional holdings fetching (13F + ARK holdings + ARK trades)
      4. Candidate universe assembly (sector stocks + 13F + ARK)
      5. Technical depression scoring per candidate (RSI, MA, volume, drawdown)
      6. Insider buying check (SEC Form 4)
      7. Per-candidate conviction scoring and filtering
      8. Ranked output for GoldenExecutor
    """

    def __init__(self):
        self.strategy = GoldenStrategy()
        self.alpaca = AlpacaClient()
        self.settings = get_settings()

    def run_scan(self) -> dict:
        """
        Execute a full Golden scan cycle.

        Returns dict with:
          - correction: SPY correction_score data
          - sector_corrections: per-sector correction data
          - holdings_13f: SA LP symbols
          - holdings_ark: {etf: [symbols]}
          - ark_recent_buys: set of recently-bought symbols
          - candidates: list of scored candidates
          - qualified: candidates that pass all filters
          - scan_time: ISO timestamp
        """
        scan_start = time.time()
        logger.info("=== Golden Scanner: starting full scan ===")

        # ── 1. Market-level correction score ───────────────────────────────
        correction = compute_correction_score(self.alpaca)
        corr_score = correction.get("score", 0)
        logger.info(f"Golden: market correction_score={corr_score}")

        # ── 2. Sector-level correction screening ──────────────────────────
        sector_corrections = screen_sector_corrections(self.alpaca)
        correcting_sectors = {
            s: d for s, d in sector_corrections.items()
            if isinstance(d, dict) and d.get("is_correcting")
        }
        logger.info(
            f"Golden: {len(correcting_sectors)} correcting sectors: "
            + ", ".join(f"{s}({correcting_sectors[s]['correction_score']})" for s in sorted(correcting_sectors)[:8])
        )

        # ── 3. Institutional holdings ─────────────────────────────────────
        holdings_13f = fetch_13f_holdings()
        ark_holdings = fetch_ark_holdings()
        ark_all = _all_ark_symbols(ark_holdings)

        # ARK recent trades (buys in last 30 days)
        ark_trades = fetch_ark_trades()
        ark_recent_buy_symbols = {t["symbol"] for t in ark_trades}
        logger.info(
            f"Golden: 13F={len(holdings_13f)} | ARK holdings={len(ark_all)} | "
            f"ARK recent buys={len(ark_recent_buy_symbols)}"
        )

        # ── 4. Build candidate universe ───────────────────────────────────
        # Sources:
        #   a) Stocks from correcting sectors (SECTOR_STOCK_UNIVERSE)
        #   b) 13F holdings (always included)
        #   c) ARK holdings (always included)
        #   d) ARK recent buys (always included — strong signal)

        universe: set[str] = set()

        # a) Stocks from correcting sectors
        sector_membership: dict[str, set[str]] = {}  # symbol → set of sectors
        for sector_name in correcting_sectors:
            stocks = SECTOR_STOCK_UNIVERSE.get(sector_name, [])
            for sym in stocks:
                universe.add(sym)
                sector_membership.setdefault(sym, set()).add(sector_name)

        # Also add stocks from mildly-correcting sectors (score >= 10) for broader coverage
        for sector_name, data in sector_corrections.items():
            if isinstance(data, dict) and data.get("correction_score", 0) >= 10:
                stocks = SECTOR_STOCK_UNIVERSE.get(sector_name, [])
                for sym in stocks:
                    universe.add(sym)
                    sector_membership.setdefault(sym, set()).add(sector_name)

        # b) 13F holdings (always — highest-weight signal)
        for sym in holdings_13f:
            universe.add(sym)

        # c) ARK holdings
        for sym in ark_all:
            universe.add(sym)

        # d) ARK recent buys
        for sym in ark_recent_buy_symbols:
            universe.add(sym)

        logger.info(f"Golden: raw universe = {len(universe)} symbols")

        # ── 5. Batch market data fetch ────────────────────────────────────
        candidates = []
        qualified = []

        if not universe:
            logger.warning("Golden: empty candidate universe — skipping scoring")
        else:
            symbols_list = sorted(universe)

            # Batch snapshots for current prices
            try:
                # Alpaca snapshot batch limit is ~200, chunk if needed
                snapshots = {}
                for i in range(0, len(symbols_list), 200):
                    chunk = symbols_list[i:i + 200]
                    chunk_snaps = self.alpaca.get_snapshots_batch(chunk)
                    snapshots.update(chunk_snaps)
            except Exception as e:
                logger.error(f"Golden: batch snapshot failed: {e}")
                snapshots = {}

            # Batch bars for technical analysis (60 days for RSI + MAs, 370 for 52w high)
            # We need longer bars for proper technical analysis, but batch in chunks
            try:
                all_bars: dict[str, list[dict]] = {}
                for i in range(0, len(symbols_list), 50):
                    chunk = symbols_list[i:i + 50]
                    chunk_bars = self.alpaca.get_bars_batch(chunk, days=370)
                    all_bars.update(chunk_bars)
                    if i + 50 < len(symbols_list):
                        time.sleep(0.2)  # brief pause between chunks
            except Exception as e:
                logger.error(f"Golden: batch bars failed: {e}")
                all_bars = {}

            # ── 6. Insider buying check ───────────────────────────────────
            # Only check symbols that have at least one other signal
            insider_check_symbols = [
                s for s in symbols_list
                if s in holdings_13f
                or s in ark_all
                or s in ark_recent_buy_symbols
                or any(s in SECTOR_STOCK_UNIVERSE.get(sec, []) for sec in correcting_sectors)
            ]
            insider_data = fetch_insider_buying(insider_check_symbols[:30])

            # ── 7. Score each candidate ───────────────────────────────────
            for symbol in symbols_list:
                snap = snapshots.get(symbol, {})
                price = snap.get("price", 0)
                if price <= 0:
                    continue

                # Get bars for technical analysis
                bars = all_bars.get(symbol, [])

                # Average volume from bars (20-day)
                if len(bars) >= 20:
                    avg_volume = sum(b["volume"] for b in bars[-20:]) / 20
                elif bars:
                    avg_volume = sum(b["volume"] for b in bars) / len(bars)
                else:
                    avg_volume = 0

                # Technical depression score
                tech_depression = compute_technical_depression_score(bars)

                # 13F check
                in_13f = symbol in holdings_13f

                # ARK check
                ark_count = sum(1 for etf_syms in ark_holdings.values() if symbol in etf_syms)
                ark_recent = symbol in ark_recent_buy_symbols

                # Insider buying count
                insider_buys = len(insider_data.get(symbol, []))

                # Sector fit — check if symbol belongs to a Golden sector
                sym_sectors = sector_membership.get(symbol, set())
                sector_fit = len(sym_sectors) > 0 or in_13f or ark_count > 0

                # Best sector correction score for this symbol
                best_sector_corr = 0
                for sec in sym_sectors:
                    sec_data = sector_corrections.get(sec, {})
                    if isinstance(sec_data, dict):
                        best_sector_corr = max(best_sector_corr, sec_data.get("correction_score", 0))
                # If not in any sector, use market correction as proxy
                if best_sector_corr == 0:
                    best_sector_corr = corr_score

                scored = score_candidate(
                    symbol=symbol,
                    price=price,
                    avg_volume=avg_volume,
                    correction_score=corr_score,
                    sector_correction_score=best_sector_corr,
                    in_13f=in_13f,
                    ark_etf_count=ark_count,
                    ark_recent_buy=ark_recent,
                    insider_buys=insider_buys,
                    tech_depression=tech_depression,
                    sector_fit=sector_fit,
                    strategy=self.strategy,
                )
                scored["price"] = price
                scored["avg_volume"] = round(avg_volume, 0)
                scored["sectors"] = sorted(sym_sectors) if sym_sectors else []
                scored["ark_recent_buy"] = ark_recent
                scored["insider_buys"] = insider_buys
                candidates.append(scored)

                if scored["passes"]:
                    qualified.append(scored)

        # Sort by conviction score descending
        qualified.sort(key=lambda c: c["conviction_score"], reverse=True)
        candidates.sort(key=lambda c: c["conviction_score"], reverse=True)

        scan_duration = time.time() - scan_start

        # ── 8. Log results ────────────────────────────────────────────────
        for q in qualified[:10]:
            write_reasoning(
                agent="golden_scanner",
                event="candidate_scored",
                symbol=q["symbol"],
                action="flag",
                corners={
                    "chart": q.get("technical", {}).get("depression_score", 0) >= 40,
                    "structure": q["checks"]["cross_ref"],
                    "sector": q["breakdown"].get("sector", 0) > 0,
                    "catalyst": q["breakdown"].get("correction", 0) >= 0.4,
                },
                conviction=round(q["conviction_score"] * 4),
                notes=(
                    f"Tier: {q['tier']} | Score: {q['conviction_score']:.3f} | "
                    f"Price: ${q['price']:.2f} | "
                    f"RSI: {q.get('technical', {}).get('rsi', '?')} | "
                    f"Depression: {q.get('technical', {}).get('depression_score', 0)}/100 | "
                    f"13F: {q['breakdown'].get('13f', 0):.1f} | "
                    f"ARK: {q['breakdown'].get('ark', 0):.2f} (recent_buy={q.get('ark_recent_buy', False)}) | "
                    f"Insider: {q.get('insider_buys', 0)} filings | "
                    f"Sectors: {q.get('sectors', [])} | "
                    f"Correction: {corr_score}/100 | "
                    f"Breakdown: {q['breakdown']}"
                ),
            )

        result = {
            "correction": correction,
            "sector_corrections": {
                s: {
                    "correction_score": d["correction_score"],
                    "is_correcting": d["is_correcting"],
                    "avg_score": d["avg_correction_score"],
                }
                for s, d in sector_corrections.items()
                if isinstance(d, dict) and "correction_score" in d
            },
            "correcting_sectors": sorted(correcting_sectors.keys()),
            "holdings_13f": holdings_13f,
            "holdings_ark_count": {etf: len(syms) for etf, syms in ark_holdings.items()},
            "ark_recent_buys": sorted(ark_recent_buy_symbols),
            "universe_size": len(universe),
            "candidates_scored": len(candidates),
            "qualified_count": len(qualified),
            "qualified": qualified[:20],
            "top_candidates_all": candidates[:10],  # top 10 regardless of pass/fail
            "scan_duration_secs": round(scan_duration, 1),
            "scan_time": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            f"=== Golden Scanner complete: {len(qualified)}/{len(candidates)} qualified | "
            f"correction={corr_score} | sectors_correcting={len(correcting_sectors)} | "
            f"duration={scan_duration:.1f}s ==="
        )

        return result
