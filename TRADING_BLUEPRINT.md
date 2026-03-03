# TRADING BLUEPRINT
## Newman Strategy — Operational Specification for a High-Reasoning Agent

> **Purpose:** This document describes the complete intent, logic, and psychological framework of the Newman trading system. It is written for an intelligent agent, not a compiler. Every rule here exists for a reason. Understand the reason before applying the rule.

---

## PART I — WHO IS NEWMAN, AND WHY DOES THIS MATTER

This system is modelled on Jeffrey Newman, a trader who grew $2,500 into $50M over 17 years. His win rate was below 50%. He compounded at roughly 80% annually. The secret is not accuracy — it is **asymmetry**: losses are capped at 5–8%, winners are held until 50–100%+. One large win covers many small losses and still produces significant profit.

The psychological profile that produced this result:
- **INTJ ("The Architect"):** Systematic, evidence-driven, deeply private. Does not seek validation from others about positions.
- **D/C "Producer" (DISC):** Decisive at entry, disciplined at exit. No second-guessing after the rule fires.
- **95th percentile Openness:** Genuinely curious about emerging themes — gets interested in things before they are mainstream.
- **10th percentile Extraversion:** Does not broadcast positions. Does not look for agreement. Privacy protects edge.

The most important thing an agent operating this system can internalize: **the goal is not to be right. The goal is to lose small and win big.** A 40% win rate with a 10:1 W/L ratio produces extraordinary returns. A 70% win rate with a 1:1 W/L ratio produces mediocrity.

---

## PART II — THE SEVEN-STEP PIPELINE

The Newman system operates as a sequential pipeline. A stock must pass every earlier gate before reaching the next one. Think of it as a funnel: hundreds of stocks enter at the top; at most a handful reach execution.

```
Universe (all tradeable US equities)
        ↓
[Step 1] Theme Detection — is a sector heating up?
        ↓
[Step 2] Watchlist Construction — which stocks are in that sector?
        ↓
[Step 3] Share Structure Filter — is the stock structurally clean?
        ↓
[Step 4] Breakout Scanner — is the chart signalling NOW?
        ↓
[Step 5] Shotgun Entry — open a small starter position
        ↓
[Step 6] Pyramid Scaling — add size only after the stock proves itself
        ↓
[Step 7] Risk Management & Exit — close the position at the right time
```

---

## PART III — STEP 1: THEME DETECTION

### Intent
Find the sectors that are beginning to attract genuine attention — news coverage, social discussion, and institutional money flows — **before** mainstream media covers them. The edge is earliness. Once the theme is on the front page of Bloomberg, the trade is largely over.

### How Scoring Works
Three independent signals are blended into a single composite score between 0 and 1:

| Source | Weight | What it measures |
|--------|--------|-----------------|
| News | 40% | Catalyst keyword frequency in recent news articles |
| Social | 30% | Reddit and Twitter mention volume and sentiment |
| ETF Performance | 30% | Sector ETF price and volume behaviour over the last month |

The composite formula weights news most heavily because named catalysts (FDA decisions, legislation, contracts) are the most reliable precursors to sustained moves. Social and ETF signals confirm that money and attention are actually moving, not just speculated about.

### Theme Status Classification

| Score | Status | Meaning for the agent |
|-------|--------|----------------------|
| Above 0.6 | HOT | Sector is actively moving. Priority watchlist population. |
| 0.3 – 0.6 | EMERGING | Sector is warming up. Monitor closely, begin building watchlist. |
| Below 0.3 | COOLING | Signal is fading. Do not initiate new positions in this theme. |

Any theme scoring above 0.1 is retained in the database. Below 0.1, the signal is too weak to act on — discard.

### What Qualifies as a Catalyst (News Corner)
A catalyst is a specific, verifiable event that changes the investable case for a sector. The following words in a news headline are indicators that a real catalyst may be present: **approval, legalization, breakthrough, pilot program, clinical trial, mandate, regulation, merger, acquisition, partnership, FDA, patent, contract, award, launch**. A story containing multiple of these words in a 7-day window carries more weight than a single mention.

### Social Signal Rules
- Reddit: a ticker must be mentioned at least 3 times in a monitoring window to register as a signal. Fewer mentions is noise.
- Twitter: the system requires more than 10 tweets about a theme to score it. Below that threshold, it is considered insufficient signal.
- Neither platform is treated as authoritative alone. Social confirms news; news doesn't confirm social.

### ETF Performance Rules
Sector ETFs are treated as a collective "vote" from institutional and professional money. The scoring is:
- If the sector ETF gained more than 3% in the past week, that is a meaningful short-term signal.
- If the sector ETF gained more than 10% in the past month, that is a sustained trend — weight it more heavily.
- If the ETF's trading volume is running more than 1.5× its normal level, institutions are actively rotating into the sector.

### Decision Criteria: Should This Theme Be Acted On?
**YES** — composite score above 0.3 AND at least one named catalyst present in recent news.
**WAIT** — composite between 0.1 and 0.3 with ETF or social signal building.
**NO** — composite below 0.1 or signal is declining week-over-week.

---

## PART IV — STEP 2: WATCHLIST CONSTRUCTION

### Intent
For each hot or emerging theme, identify every stock that could benefit from the catalyst. The goal is to cast a wide net first, then filter aggressively. You want the stock that moves the most — and in this universe, that is almost always the one with the smallest float in the hottest sub-sector.

### Candidate Discovery (Priority Order)
The system uses five methods to find stocks in a theme, tried in sequence:

1. **Keyword symbol search** — query financial data APIs for tickers matching the theme's keywords. Broad but fast.
2. **Industry peer expansion** — start from known seed stocks in the theme and pull their industry peers. This finds related names that keyword search misses.
3. **ETF holdings extraction** — look inside the sector ETF's holdings list. Every stock the ETF owns is by definition in the theme.
4. **ETF ticker mapping** — use a pre-built map of themes to their primary ETFs, then extract holdings from those.
5. **Hardcoded sector fallback** — if all API methods return fewer than 5 symbols, use a curated list of known names in that sector. This is a safety net, not the primary method.

### Watchlist Limits
A maximum of 30 stocks per theme are maintained. Beyond that, the list becomes unmanageable and dilutes attention. Quality over quantity — you want the 5–10 best setups, not 30 mediocre ones.

### What Gets Stored Per Stock
For each watchlist candidate, the system records: price, average daily volume over 5 days, market capitalisation, float shares, shares outstanding, and the theme it belongs to. This information is the raw material for Step 3.

---

## PART V — STEP 3: SHARE STRUCTURE FILTER

### Intent
Newman's edge requires stocks with small floats. A small float means that when a catalyst arrives and volume surges, there are few shares available to absorb the demand — price moves sharply. Large-float stocks absorb demand without moving much. The structure filter eliminates every stock that cannot exhibit the kind of explosive, asymmetric price move the strategy requires.

### Hard Filters — All Three Must Pass

**Float under 200 million shares.**
This is the primary structural requirement. Float is the number of shares actually available for public trading (excluding locked-up insider and institutional holdings). A float above 200M means the stock is too large and liquid to move dramatically on a sector catalyst. This is not a suggestion — it is a hard gate.

*Why this number:* Stocks with floats under 50M are ideal. Stocks between 50M and 100M are good. Stocks between 100M and 200M are acceptable if the other signals are very strong. Above 200M, the edge evaporates.

**Price above $0.50.**
This eliminates true penny stocks with exchange-related risks, illiquid spreads, and potential delisting issues. It is a risk management floor, not a quality signal. A $0.49 stock is not worse than a $0.51 stock by any fundamental measure, but the operational risks below $0.50 (wide spreads, limited broker support, potential Alpaca restrictions) make it a practical cutoff.

**Average daily volume above 100,000 shares.**
The system must be able to enter and exit positions without moving the market. Below 100,000 shares/day, filling even a $2,500 starter position becomes difficult, and exits in a volatile situation become dangerous. Minimum liquidity is a survival requirement.

### Ranking Within the Watchlist
Once stocks pass all three filters, they are ranked by priority for the breakout scanner:

- **Float size is the dominant ranking factor.** Smaller float = higher rank. A stock with a 5M share float that passes the filters is more interesting than one with a 180M float.
- **Volume** as a secondary factor: higher daily volume means better liquidity, easier exits.
- **Bonus points** if the stock has a confirmed catalyst type or is already showing a near-breakout signal from a previous scan.

### Decision Criteria: Does This Stock Pass Structure?
**PASS** — float under 200M, price over $0.50, and average volume over 100,000 shares daily.
**FAIL** — any one of these three conditions is not met. Remove from watchlist immediately.
**DATA GAP** — if float data is unavailable, do not assume it qualifies. Flag it and use Alpha Vantage to enrich the data before rescanning.

---

## PART VI — STEP 4: THE BREAKOUT SIGNAL

### Intent
This is the core of the entire system. The entry signal is not "the stock went up today." It is something far more specific: the stock has been in a **multi-year downtrend**, and today it has broken above the declining resistance line that defined that downtrend. This is a structural change — the stock is no longer in the same regime it was in. It is transitioning.

Newman does not trade momentum. He trades **regime change** — the moment a beaten-down, forgotten stock in a hot sector begins to move again after years of decline.

### The Trendline Resistance Break — Explained

**What the trendline is:**
Look at the stock's price history over the past 252 trading days (approximately one calendar year). Find the local peaks — the points where price reached a high and then declined. Draw a straight line through those peaks, starting from the oldest and connecting to the most recent. If that line is sloping downward, the stock is in a downtrend. That line is the resistance.

**What a break means:**
When today's closing price rises **more than 1% above that resistance line**, the stock has broken out. It has, for the first time in months or years, traded above the ceiling that has been suppressing it. This is the signal.

**Why 1% clearance, not just "above the line":**
Price is noisy. A close that is exactly at the resistance line, or just barely above it, could be a one-day anomaly that reverses the next session. The 1% clearance requirement means the break is real — the stock has genuinely cleared the resistance, not just touched it.

**The look-ahead constraint:**
The resistance line is calculated using only the bars that occurred before today. Today's bar is never included in the trendline calculation. This ensures the signal is not retroactively fitted to data that wasn't available at the time of the decision.

### The Four Conviction Corners

The breakout signal alone is necessary but not sufficient. The system requires at least 2 of 4 additional confirmation signals — called "corners" — before treating a breakout as actionable.

**Corner 1 — Chart (Trendline Break)**
The resistance break described above. This is always the first corner and is required for the catalyst corner check to even run. Without a chart break, no entry is considered.

*Intent:* Ensure we are entering at a structurally significant moment, not a random daily fluctuation.

**Corner 2 — Structure (Volume Surge)**
Today's trading volume is at least 2.5 times the 20-day average volume. The multiplier is 2.5×, not 2×, because the strategy requires confirmation that unusual interest — not just normal daily variation — is driving the price.

*Intent:* Volume is the fingerprint of institutional and professional money. When price breaks resistance with unusually high volume, it signals that sophisticated participants are accumulating, not that retail traders are buying randomly. A resistance break on normal volume is a false alarm; a break on 3× volume is a genuine signal.

**Corner 3 — Sector (Price Zone)**
The stock's current price is within 20% of its 52-week high. Equivalently: the stock is trading at 80% or more of where it peaked in the last year.

*Intent:* This filters out stocks that have broken resistance but are still deeply depressed — say, a stock that peaked at $10 and is now at $1.50 breaking a $2 resistance line. Such a stock is not in "active breakout territory." The sector-corner requires that the stock is in a zone where genuine momentum buyers operate: near multi-year highs, not near multi-year lows.

**Corner 4 — Catalyst (Recent News)**
A news article published within the last 48 hours contains at least one of the following words in its headline or summary: *approval, approved, FDA, contract, patent, breakthrough, partnership, acquisition, deal, award, grant, legalization, license, regulatory, clinical trial, phase 3, phase 2, earnings beat, revenue beat, upgraded, buyout, merger, government, IPO, listing, strategic*.

*Intent:* The chart tells you that price is breaking out. The catalyst tells you why. A breakout without a catalyst is a technical event that lacks a fundamental anchor — it can reverse quickly. A breakout with a catalyst has a story that will attract new buyers and sustain the move. The catalyst corner is the fourth corner precisely because the other three corners can exist without a named catalyst; but when all four align, the conviction is highest.

### The SPY Regime Gate

Before any entry signal is acted on, the broad market must be in a bull regime. The system checks whether SPY (the S&P 500 ETF proxy) has risen more than 2% over the past 20 trading bars.

**If SPY is in a bull regime:** entry signals proceed to evaluation.
**If SPY is NOT in a bull regime:** ALL entry signals are blocked, regardless of conviction score. The pipeline continues to run (scans still happen, reasoning is still logged) but no new positions are opened.

*Intent:* Individual stock breakouts that occur against a deteriorating broad market have a much lower success rate. The sector rotation that powered the theme can quickly reverse when the overall market is falling. Protecting capital in bear markets is not optional — it is the mechanism that enables survival long enough to participate in bull markets.

*An important nuance:* If SPY data is unavailable or the check fails for technical reasons, the gate defaults to OPEN (allowing entries). The intent is to protect against knowable bear markets, not to block trading due to data outages.

### Minimum Conviction Requirement
A stock must score at least 2 out of 4 corners to be flagged as an entry signal. A score of 1 is not enough — even with a trendline break, if neither volume nor sector nor catalyst confirm it, the signal is weak. A score of 3 or 4 represents a high-conviction setup.

*How conviction maps to action:*
- 1 corner: No entry. Log the scan for monitoring. Recheck tomorrow.
- 2 corners: Entry permitted. Open the starter position.
- 3 corners: Strong entry. Open the starter position and monitor closely for pyramid opportunity.
- 4 corners: Maximum conviction. Rare. Treat as highest priority.

### Decision Criteria: Is This a Valid Entry Signal?
**YES** — trendline break confirmed AND at least 2 corners active AND SPY in bull regime.
**BLOCKED** — SPY not in bull regime. Log the signal but do not execute.
**WEAK** — trendline break confirmed but only 1 corner active. Do not enter. Monitor.
**NO SIGNAL** — no trendline break detected. Skip entirely.

---

## PART VII — STEP 5: SHOTGUN ENTRY

### Intent
The starter position is a **hypothesis**, not a commitment. Newman's principle is: express interest in the trade with the minimum amount of capital, then let the stock prove itself before adding size. The $2,500 starter is the "ticket to the game." You are paying for the right to pyramid later.

The term "shotgun entry" reflects the philosophy: you are not trying to time the exact perfect moment. You are getting in when the signal fires, accepting that you might be early by a session or two, with a fixed small loss if you are wrong.

### Pre-Entry Checklist — All Must Pass

**1. No existing position in this symbol.**
The system does not average down or open second positions in stocks already held. If you own ACME, you manage that position through pyramiding or exit. You do not open a new ACME entry.

**2. Kill switch is not paused.**
If the kill switch has been engaged (via the dashboard STOP ALL button or WhatsApp command), no new positions are opened. This is a hard block. The reason is always logged.

**3. Stopped-out cooldown has expired.**
If this symbol was stopped out within the last 24 hours, it is blocked from re-entry. *Intent:* A stock that just stopped you out is telling you something. Maybe the catalyst was fake, maybe the breakout was a trap, maybe the sector is reversing. Waiting 24 hours before re-entering forces a re-evaluation rather than a reflexive re-entry that compounds a loss.

**4. Sufficient cash is available.**
The account must have at least $2,500 in available buying power. Never open a position by borrowing (margin) beyond the configured limits.

**5. The resulting position is at least 1 share.**
If the stock price is so high that $2,500 buys fewer than 1 share, do not enter. The system cannot operate at fractional-share precision in this context.

### Position Sizing
The starter position is a flat $2,500 regardless of conviction level. This is intentional. Sizing up the starter based on conviction would mean taking larger initial losses on the trades that don't work — and the whole system is built around containing initial losses. The asymmetry is achieved through pyramiding winners, not through big starters.

### Stop Loss Placement
Immediately upon entry, a hard stop is set based on the stock's Average True Range (ATR), which measures how much the stock normally moves day to day.

**ATR-based stop:** Set the stop at the entry price minus 1.5 times the ATR.
**Floor protection:** The stop cannot be more than 5% below entry, regardless of ATR. If 1.5× ATR would put the stop 8% below entry, the stop is placed at 5% below entry instead.

*Intent:* The ATR-based stop respects the stock's own volatility. A stop that is too tight (say, 1% on a stock that normally moves 3% per day) will get hit by normal noise. A stop that accounts for typical daily movement only fires on genuine adverse moves. The 5% floor ensures we never accept a loss larger than 5% on the initial position, regardless of how volatile the stock is.

### Immediately-Wrong Monitor
For the first 15 minutes after entry, a separate monitoring process watches the stock's price every 60 seconds.

**Trigger:** If the price falls more than 1× ATR below the entry price within the 15-minute window, exit the entire position immediately.

*Intent:* Newman's most famous rule is "if the stock doesn't act right in the first 15 minutes, get out." A stock that immediately reverses after your entry is telling you that the signal was wrong — either the breakout was a fake-out, the market absorbed the volume without buyers following through, or something changed. Rather than waiting for the ATR stop (which might be 5% away), the immediately-wrong rule exits at roughly half that loss. Smaller losses mean more remaining capital for the next setup.

*An important nuance:* This rule only applies to the first 15 minutes. After that window, the position is managed by the normal stop and trendline exit logic.

---

## PART VIII — STEP 6: PYRAMID SCALING

### Intent
The pyramid is where the asymmetric returns come from. Most of the initial entry positions will either be stopped out small or will move sideways and eventually exit flat. A minority will work dramatically well. The pyramid rule ensures that when a position IS working, the system adds significant capital behind it — turning a $2,500 starter into a $20,000+ position in a stock that has confirmed the thesis.

Newman's phrase: "nibble first, then go all-in once confirmed." The pyramid is the mechanism that operationalises this.

### Pyramid Trigger Levels
Each tier adds capital to the position once the unrealised profit percentage reaches the threshold:

| Tier | Profit Required | Capital Added |
|------|----------------|---------------|
| 1 (first add) | +3% unrealised gain | 2% of total portfolio value |
| 2 (second add) | +8% unrealised gain | 5% of total portfolio value |
| 3 (third add) | +15% unrealised gain | 10% of total portfolio value |
| 4 (fourth add) | +25% unrealised gain | 10% of total portfolio value |

*Why percentage of portfolio, not flat dollar amounts:* The account grows over time. As the account grows, the add sizes grow proportionally — this is how compounding works in practice.

*Why these specific thresholds:* At 3%, the stock has proven it can move in the right direction but hasn't gone far enough to confirm a trend. This is a "show of hands" — a small add to express continued belief. At 8%, the stock is establishing itself. At 15%, it is a genuine winner. At 25%, it has fully confirmed the thesis and deserves maximum commitment.

### Pyramid Limits

**Maximum 4 pyramid levels.** After 4 adds (including the starter), no further size is added regardless of how well the stock performs. The position is managed only via exit rules from this point.

**Maximum 35% of portfolio in any single stock.** If adding the next pyramid tier would push a single position above 35% of the total portfolio value, the add is blocked. This prevents a single position from becoming existential to the account.

**Maximum 60% of portfolio in any single theme.** If total exposure to a theme (across all stocks in that theme) would exceed 60% after the add, the add is blocked. This prevents the account from being destroyed by a single sector reversal.

*Intent of both limits:* The strategy works because of diversification across many setups over time. Concentrating 80% of the account in one stock — even a great one — violates the core risk management principle. Preservation of the account is the highest priority.

### Decision Criteria: Should This Pyramid Add Be Executed?
**YES** — unrealised profit meets the tier threshold AND position is below 35% of portfolio AND theme is below 60% of portfolio AND fewer than 4 prior adds exist.
**NO (position limit)** — adding would breach the 35% single-stock limit.
**NO (theme limit)** — adding would breach the 60% theme limit.
**NO (max levels)** — 4 pyramid levels already executed.

---

## PART IX — STEP 7: RISK MANAGEMENT AND EXIT

### Intent
The exit decision is the most psychologically difficult part of trading. Most traders exit winners too early (taking small profits to feel good) and hold losers too long (hoping for recovery). The Newman system uses three exit mechanisms in a specific priority order to remove psychology from the equation.

### Exit Priority Hierarchy

The system evaluates exits in the following order. The first condition that is true fires the exit. Lower-priority conditions are not evaluated if a higher-priority one has already triggered.

---

**Priority 1: Immediately-Wrong Exit (first 15 minutes only)**
Already described in Step 5. If price drops more than 1× ATR below entry within 15 minutes of opening the position, exit immediately.

*Why it is highest priority:* A position that goes wrong immediately has not had time to develop any trend. There is no trendline to break, no profit to protect. The only appropriate response is to exit with a small loss before the full stop is hit.

---

**Priority 2: Hard ATR Stop**
If the closing price falls to or below the stop loss price (set at entry as `entry price minus 1.5× ATR`, with a 5% floor), exit the full position at the next open.

*Intent:* This is the defined maximum loss for the trade. When this fires, it means the thesis is wrong — the stock has moved adversely by more than its normal volatility range. There is no "let's see if it recovers." The stop fires, the loss is booked, the 24-hour cooldown begins, and the account moves on.

*An important psychological note:* The stop exists precisely so that this decision does not require judgment at the moment it fires. The judgment was made when the stop was set at entry. When price hits the stop, execution is automatic.

---

**Priority 3: Uptrend Trendline Break (primary managed exit)**
This is the mirror image of the entry signal. Just as the entry fires when price breaks above a declining resistance line, this exit fires when price breaks below a rising support line.

*How the support line is constructed:*
After the position is established, the system tracks the price's swing lows — the points where price dipped temporarily and then recovered. A rising line drawn through those lows is the uptrend support. As long as price stays above this line, the trend is intact and the position is held. When the closing price falls more than 1% below this line, the trend is considered broken.

*Conditions required for this exit to fire:*
1. The position must be in unrealised profit (this prevents exiting a losing position on a trendline break — that would be worse than just taking the stop).
2. The position must be at least 6 bars old (to allow the trendline to form meaningfully).
3. Price must close more than 1% below the support line.

*Why this is the primary managed exit:* The uptrend trendline captures the natural behaviour of a stock in a genuine breakout — it trends with intermittent pullbacks that stay above the rising support line. When the stock eventually stalls or reverses, the trendline gives a structured exit signal based on the actual behaviour of the stock, rather than an arbitrary percentage target.

*Why it needs 1% clearance below the line:* Same reason as the entry signal — noise. A close that is 0.1% below the support line is probably not a real break.

---

**Priority 4: Profit Tier Scale-Out (fallback)**
This is only used when the uptrend trendline has not yet formed (too few bars) or when the position is profitable and approaching round-number gain levels. At each tier, 33% of the remaining position is sold:

| Tier | Unrealised Gain | Action |
|------|----------------|--------|
| Tier 1 | +15% | Sell 33% of position |
| Tier 2 | +30% | Sell 33% of remaining position |
| Tier 3 | +45% | Sell all remaining shares |

*Intent:* These tiers are a fallback, not the primary exit mechanism. The preferred exit is the trendline break because it can allow a position to run 100%, 200%, or more — the tiers cap it at 45%. However, in the early phase of a position (before enough swing lows exist to form a trendline), the tiers provide a structured profit-taking mechanism that prevents a winning trade from turning into a losing one.

---

**Priority 5: Media Saturation Signal (judgment-required)**
When the theme and/or specific stock has been covered by mainstream financial media (Bloomberg, CNBC, Wall Street Journal, widespread retail discussion), this is an exit signal. The crowd has arrived. The edge has evaporated. This is the "golf course indicator" — when your golf partner asks about the stock, get out.

*This exit requires judgment:* Unlike the other exits, media saturation cannot be fully automated because "mainstream coverage" is qualitative. The system can detect volume and social activity spikes that often accompany saturation, but the agent should flag this as a condition requiring human review.

### ATR Calculation
The Average True Range (ATR) is calculated over 14 bars using Wilder's smoothing method. True Range for each bar is the largest of: (high − low), (high − previous close), (previous close − low). The ATR is then the smoothed average of True Range values.

*Why 14 bars:* Industry standard that balances responsiveness to recent volatility with smoothing of noise.

---

## PART X — THE FOUR CORNERS DECISION FRAMEWORK (PSYCHOLOGICAL FILTER)

This section describes the psychological, not just mechanical, application of the four corners.

### The Corners as a Pre-Commitment Device
Newman checks four corners before adding size. The purpose is not just analytical — it is psychological. By requiring four specific, pre-defined criteria to be met, the trader (or agent) cannot rationalize entering a trade that "feels right" without evidence. The corners are the commitment made in advance that prevents emotion-driven decisions in the moment.

### Applying Conviction to Sizing

| Active Corners | Entry Decision | Sizing Intent |
|---------------|----------------|---------------|
| 0 | Do not enter | — |
| 1 | Do not enter | Signal too weak |
| 2 | Starter only | Hypothesis mode — $2,500 flat |
| 3 | Starter with high pyramid intent | Watch closely, expect to add at Tier 1 |
| 4 | Starter immediately + maximum pyramid readiness | Rare setup. Let it run. |

### The Asymmetric Mindset in Practice
When evaluating a setup, the agent should frame the question as: *"What is the maximum this can return if right, vs. what is the maximum I lose if wrong?"*

- If wrong, the loss is defined: 5% of $2,500 = $125, or the immediately-wrong exit fires at ~3% = $75.
- If right and pyramided to 4 levels, a 50% gain on a $20,000 position = $10,000.

The asymmetry is roughly 80:1 on the maximum outcomes. The trade makes sense even with a 40% success rate because the expected value is strongly positive.

### The "Stock Acts Right" Test
Beyond the mechanical corners, Newman uses one qualitative filter: does the stock "act right"? This means:
- After entry, price continues in the direction of the breakout.
- Volume stays elevated (not a one-day spike that fades).
- The stock holds above the resistance level it broke (old resistance becomes new support).
- The sector continues to attract news and social attention.

If any of these are failing after 2–3 days, the stock may not be a genuine breakout. The agent should flag this for review even if the mechanical stops haven't fired yet.

---

## PART XI — GO / NO-GO PROTOCOL (PAPER-TO-LIVE GATE)

### Intent
Before committing real money, the system must demonstrate that the strategy works in paper trading with the specific data, execution, and market conditions of this account. The Go/No-Go protocol defines exactly what "works" means, in advance — so the criteria cannot be retroactively adjusted to justify going live.

### Performance Gates (Phase 1 — Wide Gate, 4-Day Minimum)

These thresholds are intentionally wide because Phase 1 has a tiny sample size (3–5 trades). Statistical significance requires at least 20+ trades. The Phase 1 gate only ensures the system is not catastrophically broken.

| Criterion | Threshold | Why This Number |
|-----------|-----------|----------------|
| Closed paper trades | At least 3 | Cannot evaluate with fewer than 3 data points |
| Paper trading history | At least 4 calendar days | Need multiple market sessions |
| Win rate | At least 40% | Break-even floor for a W/L ratio of 1.5× |
| W/L ratio | At least 1.5× | Avg winner must be 1.5× the avg loser to cover 40% wins |
| Profit factor | At least 1.1 | Gross wins exceed gross losses by 10%. This is the binding gate. |
| Max drawdown | At most 35% | Wide tolerance for small sample. Tighten to 25% at 20+ trades. |

**The profit factor is the binding gate.** It is the most robust measure for small sample sizes because it captures both the magnitude and frequency of wins vs. losses in a single number. A profit factor below 1.1 means the system is losing money regardless of win rate.

### System Health Gates

| Criterion | Requirement | Why |
|-----------|-------------|-----|
| Alpaca API connection | Must be reachable | Cannot trade without live data and execution |
| Paper mode | Must be True | Confirm we are not accidentally in live mode |
| Engine state | Must not be paused | Kill switch must be off before going live |
| Scanner activity | Must have run within 25 hours | Confirms the scanning infrastructure is operational |

The scanner activity gate is advisory-only (it does not block Go verdict) because the scanner legitimately doesn't run on weekends or outside market hours. All other system health gates are blocking.

### Verdict Logic
If any blocking criterion fails, the verdict is NO-GO. If all blocking criteria pass, the verdict is GO. A GO verdict does not mean "go live immediately" — it means the minimum evidence threshold has been met. The human operator still makes the final decision to flip from paper to live.

### Tightening Thresholds Over Time
The Phase 1 thresholds are explicitly wide because of the small sample. Once the account has 20+ closed trades and 30+ days of history, the thresholds should be tightened:
- Win rate target: raise to 45%
- W/L ratio target: raise to 2.0×
- Profit factor target: raise to 1.5+
- Max drawdown limit: lower to 25%

---

## PART XII — KILL SWITCH AND EMERGENCY OVERRIDE PROTOCOL

### Intent
The kill switch exists for situations where immediate, unconditional trading cessation is required — regardless of what the rules say about individual positions. Market crashes, data anomalies, execution errors, and personal emergencies are all valid reasons to stop trading instantly.

### Kill Switch States
The kill switch has two states: **active (paused)** and **inactive (running)**. When paused:
- No new positions are opened. Every entry check in the trade executor begins by checking this flag.
- Existing positions continue to be monitored for stop-loss and exit conditions.
- The reason for the pause and the timestamp are recorded and visible in the dashboard.

### Override Commands (WhatsApp)
The system accepts commands via WhatsApp from a single authorised number. Only messages from this number are processed. Others are silently ignored.

| Command | Action |
|---------|--------|
| STOP or STOP ALL | Pause the engine AND close every open position immediately via Alpaca |
| STOP [SYMBOL] | Close a single position immediately. Does not pause the engine. |
| CLOSE [SYMBOL] | Identical to STOP [SYMBOL] |
| PAUSE | Pause new entries. Does not close existing positions. |
| RESUME | Clear the pause and allow new entries again. |
| STATUS | Return a live snapshot: portfolio value, open positions, daily P&L, kill switch state. |

### Dashboard Override Controls
The same controls are available in the dashboard:
- **STOP ALL button:** Closes all positions and pauses the engine. Requires confirmation click.
- **RESUME button:** Clears the pause. Only visible when paused.
- **Individual Close button per position:** Closes a single position without affecting others.

---

## PART XIII — DATA SOURCES AND ALPACA MCP TOOLS

### Primary Market Data & Execution: Alpaca

Alpaca is the sole execution venue and primary real-time market data source. All orders (buys, sells, closes) are routed through Alpaca. All real-time price data used for stop-loss monitoring, position valuation, and the immediately-wrong check comes from Alpaca.

**Key operational tools provided by the Alpaca integration:**

| Tool | Purpose |
|------|---------|
| `get_account()` | Returns current equity, cash, buying power, daily P&L. Used by the dashboard and Go/No-Go check. |
| `get_positions()` | Returns all open positions with current prices and unrealised P&L. Used by risk manager. |
| `place_market_order(symbol, qty, side)` | Executes buys and sells. Used for all entries, pyramid adds, and exits. |
| `close_position(symbol)` | Emergency close for a single symbol. Used by kill switch and override commands. |
| `get_bars(symbol, days, timeframe)` | Historical OHLCV bars for a single symbol. Used for trendline calculation and ATR. |
| `get_bars_batch(symbols, days)` | Same as above for multiple symbols in one call. Used by the breakout scanner for efficiency. |
| `get_snapshot(symbol)` | Latest trade price, daily bar, previous close. Used for real-time P&L and ticker tape. |
| `get_snapshots_batch(symbols)` | Batch snapshot for multiple symbols. Used by the ticker tape strip on the dashboard. |
| `get_latest_quote(symbol)` | Live bid/ask for a single symbol. Available for spread-checking before entry. |
| `get_avg_volume(symbol, days)` | Calculated average volume. Used as baseline for volume surge detection. |

**Alpaca account is running in paper mode.** The configuration flag `alpaca_paper = True` connects to the paper trading endpoint. The Go/No-Go gate confirms this is True before any live transition.

### News Data: Finnhub

Finnhub provides two critical inputs:
1. **General market news** — scanned for catalyst keywords during theme detection.
2. **Company-specific news** — scanned for catalyst keywords when a trendline break is detected. This is what powers the Catalyst corner check. Only called when a trendline break already exists, to limit API usage.

Rate limit: 60 calls per minute. The system enforces a minimum 1-second interval between Finnhub calls.

### News Aggregation: Perigon

Perigon supplements Finnhub with a broader news search. During theme detection, Perigon is queried for each of the top catalyst keywords over a 7-day window, returning up to 10 articles per keyword. Perigon provides higher recall than Finnhub alone for niche sector stories.

### Social Signals: Reddit (via PRAW)

Reddit scanning targets sector-specific subreddits during theme detection. A ticker must appear at least 3 times in the monitored window to register as a social signal. Fewer mentions is noise. The social weight (30%) in the theme score reflects the fact that Reddit activity often precedes price moves but is also susceptible to manipulation and groupthink.

### Social Signals: Twitter/X (via Tweepy)

Twitter searches are run for each theme's keywords. A minimum of 10 tweets is required before the social signal is scored for that theme. Twitter's API is rate-limited and the system caps at 5 theme queries per scan to stay within limits.

### Fundamental Data: Alpha Vantage

Used for two purposes: (1) symbol keyword search when building the watchlist, and (2) enriching float and market cap data for watchlist items when Finnhub data is incomplete. Free tier is limited to 25 requests per day — queries are batched and cached to stay within this limit.

### ETF Holdings: Internal Mapping

A pre-built map connects each of 15+ themes to their primary sector ETFs (e.g., cannabis → MJ, solar → TAN, robotics and AI → ARKQ). The ETF performance data comes from Alpaca bars. The holdings lists are either cached or pulled from a dedicated ETF holdings data source.

### Pre-Trade Audit Log

Before every order is submitted to Alpaca, the system writes a complete record to a flat file (one file per day). This record includes: event type, symbol, side, quantity, price, stop price, unrealised P&L at time of decision, theme name, conviction corners, pyramid level, and all pre-entry checks that were evaluated. This log is immutable — it can never be edited after the fact. It provides a complete audit trail of every decision.

---

## PART XIV — DAILY OPERATIONAL PROTOCOL

### Pre-Market (Before 9:30 AM ET)

1. **Verify system health** — check the Go/No-Go panel. All system health gates should be green. If Alpaca is not connected, nothing else matters.
2. **Review open positions** — check the Symbols panel for current P&L, pyramid levels, and stop prices. Are any stops dangerously close to current price?
3. **Review theme heatmap** — which sectors are HOT? Are the themes that produced open positions still HOT, or have they cooled? A cooling theme while a position is running is a warning signal.
4. **Review the Live Activity feed** — what did the scanner produce overnight or in the pre-market run? Any signals approaching the watchlist?

### During Market Hours (9:30 AM – 4:00 PM ET)

1. **Run ⟳ Scan every hour** during active market sessions. The scanner checks all clean watchlist stocks for new breakout signals.
2. **Run ⚡ Risk Check every 30 minutes** to evaluate open positions against stops, trendline breaks, and pyramid opportunities.
3. **Monitor the Live Activity feed** continuously — real-time reasoning and agent events appear here as they happen.
4. **Do not intervene in positions that are working.** If a position is above entry, the stops are not hit, and the trendline is intact — leave it alone. Impulse intervention is the enemy of asymmetric returns.
5. **Act immediately on immediately-wrong signals** — these are automated, but verify the alert fired correctly.

### Post-Market

1. **Run ▶▶ Full Pipeline** once after market close for the daily theme + watchlist refresh.
2. **Review Scanner Intelligence feed** — read the model's reasoning on each stock it scanned. Add human notes where context adds value.
3. **Review the Go/No-Go panel** — check where the performance gates stand. Which metrics are trending toward or away from thresholds?
4. **Journal any anomalies** — positions that behaved unexpectedly, scans that missed obvious setups, exits that felt early or late.

---

## PART XV — DECISION TREES FOR KEY SCENARIOS

### Scenario: A Scan Returns a Breakout Signal

```
1. Is SPY in bull regime (+2% over 20 bars)?
   → NO: Log the signal, do not execute. Wait for regime to improve.
   → YES: Continue.

2. How many conviction corners are active?
   → 0 or 1: No entry. Insufficient evidence.
   → 2+: Proceed to pre-entry checks.

3. Pre-entry checks:
   → Is there an existing position in this symbol? YES → Skip.
   → Is the kill switch paused? YES → Skip.
   → Was this symbol stopped out in the last 24 hours? YES → Skip.
   → Is cash available (≥ $2,500)? NO → Skip.
   → PASS ALL: Execute market buy of $2,500 / current price shares.

4. Post-entry:
   → Set stop at entry - 1.5×ATR (floor: entry × 0.95)
   → Start 15-minute immediately-wrong watch thread
   → Log reasoning with corners, conviction, entry price, stop price
```

### Scenario: A Position Is Being Monitored for Exit

```
1. Check immediately-wrong (first 15 min only):
   → Current price < entry - 1×ATR? YES → Exit full position. Book loss.

2. Check hard stop:
   → Current close ≤ stop price? YES → Exit full position at next open. Book loss.

3. Check uptrend trendline break:
   → Is position in profit? NO → Skip (use stop, not trendline).
   → Is position at least 6 bars old? NO → Skip (trendline not yet formed).
   → Has close broken 1% below support line? YES → Exit full position. Book gain.

4. Check profit tiers (fallback):
   → Unrealised P&L ≥ 15%? YES → Sell 33% of shares.
   → Unrealised P&L ≥ 30%? YES → Sell 33% of remaining shares.
   → Unrealised P&L ≥ 45%? YES → Sell all remaining shares.

5. None triggered: Hold. Check again next bar.
```

### Scenario: A Position Is Being Evaluated for Pyramid Add

```
1. Is unrealised P&L ≥ next pyramid threshold?
   → 3% for first add, 8% for second, 15% for third, 25% for fourth.
   → NO: Do not add. Wait.
   → YES: Continue.

2. How many pyramid levels exist?
   → Already at 4 levels? Do not add. Position is at max size.

3. Would this add breach the 35% single-stock limit?
   → YES: Do not add. Position is at max single-stock concentration.

4. Would this add breach the 60% theme limit?
   → YES: Do not add. Theme is at max concentration.

5. PASS ALL: Execute add of 2/5/10/10% of portfolio value.
   → Update average entry price and position record.
```

### Scenario: STOP ALL Is Received (via dashboard or WhatsApp)

```
1. Engage kill switch: set paused = True, log reason and timestamp.
2. For every open position:
   → Submit market sell order via Alpaca.
   → Mark position as CLOSED in the database.
   → Log each close to audit trail.
3. Return status to operator: X positions closed, engine paused.
4. All future scan signals and pyramid triggers are blocked until RESUME.
5. RESUME: set paused = False. System resumes normal operation.
```

---

## PART XVI — WHAT THE AGENT MUST NEVER DO

These are not rules — they are psychological commitments that define the boundary of the strategy:

1. **Never average down.** If a position is losing, do not buy more to lower the average entry price. The stop loss exists for exactly this situation. A losing position that is averaged down is a position that has already violated the exit rule.

2. **Never hold through a stop.** The stop fires, the position closes. There is no "I'll give it one more day." The stop price was set with deliberate judgment before the trade began. Overriding it in the moment is precisely the psychological error the rule was designed to prevent.

3. **Never re-enter a stopped-out position within 24 hours.** The cooldown is not optional. The same signal that stopped you out is likely still present in the market. Time creates perspective. Impulse re-entries after stop-outs are among the most common ways traders compound losses.

4. **Never open new positions with the kill switch paused.** Not even for "obvious" setups. The kill switch exists for situations where the operator has decided that new exposure should not be taken. Overriding it defeats its purpose.

5. **Never broadcast positions externally.** Privacy is a genuine edge in small-cap trading. Others front-running your position or your thesis can move prices and invalidate your setup. The dashboard is for internal operations only.

6. **Never size up the starter based on conviction.** The starter is flat at $2,500 always. Asymmetric returns come from pyramiding winners, not from variable starters. A larger starter means a larger loss on the majority of trades that don't work — and the strategy cannot survive that.

7. **Never take a trade without at least 2 conviction corners.** One corner is a story. Two corners is a signal. The entry checklist exists precisely to prevent "feels right" entries that have no systematic basis.

---

## APPENDIX: COMPLETE THRESHOLD REFERENCE

| Parameter | Value | Configurable | Source |
|-----------|-------|-------------|--------|
| Theme composite minimum | 0.10 | No | theme_detector |
| Theme HOT threshold | 0.60 | No | theme_detector |
| Theme EMERGING threshold | 0.30 | No | theme_detector |
| News weight in composite | 0.40 | Yes | config |
| Social weight in composite | 0.30 | Yes | config |
| ETF weight in composite | 0.30 | Yes | config |
| Reddit minimum mentions | 3 | No | theme_detector |
| Twitter minimum tweets | 10 | No | theme_detector |
| ETF weekly gain signal | +3% | No | theme_detector |
| ETF monthly gain signal | +10% | No | theme_detector |
| ETF volume surge signal | 1.5× | No | theme_detector |
| Maximum stocks per theme watchlist | 30 | No | watchlist_builder |
| Minimum candidates before fallback | 5 | No | watchlist_builder |
| Float maximum (hard filter) | 200,000,000 shares | Yes | config |
| Price minimum (hard filter) | $0.50 | Yes | config |
| Average volume minimum (hard filter) | 100,000 shares/day | Yes | config |
| Trendline lookback | 252 bars (~1 year) | No | breakout_scanner |
| Bar fetch window | 400 calendar days | No | breakout_scanner |
| Resistance clearance required | 1% above line | No | breakout_scanner |
| Volume surge multiplier | 2.5× | Yes | config |
| Sector corner proximity to high | 80% of 1-year high | No | breakout_scanner |
| Catalyst news window | 48 hours | No | breakout_scanner |
| SPY bull regime threshold | +2% in 20 bars | No | breakout_scanner |
| Minimum conviction corners | 2 of 4 | No | breakout_scanner |
| Starter position size | $2,500 | Yes | config |
| ATR stop multiplier | 1.5× | No | trade_executor |
| Stop loss floor | −5% of entry | Yes | config |
| Immediately-wrong watch duration | 15 minutes | No | trade_executor |
| Immediately-wrong poll interval | 60 seconds | No | trade_executor |
| Immediately-wrong ATR multiplier | 1.0× | No | trade_executor |
| Stopped-out cooldown | 24 hours | Yes | config |
| Pyramid Tier 1 threshold | +3% unrealised | No | trade_executor |
| Pyramid Tier 1 add size | 2% of portfolio | No | trade_executor |
| Pyramid Tier 2 threshold | +8% unrealised | No | trade_executor |
| Pyramid Tier 2 add size | 5% of portfolio | No | trade_executor |
| Pyramid Tier 3 threshold | +15% unrealised | No | trade_executor |
| Pyramid Tier 3 add size | 10% of portfolio | No | trade_executor |
| Pyramid Tier 4 threshold | +25% unrealised | No | trade_executor |
| Pyramid Tier 4 add size | 10% of portfolio | No | trade_executor |
| Maximum pyramid levels | 4 | Yes | config |
| Maximum single-stock exposure | 35% of portfolio | Yes | config |
| Maximum theme exposure | 60% of portfolio | Yes | config |
| ATR calculation period | 14 bars | No | risk_manager |
| Profit Tier 1 scale-out | +15% → sell 33% | Yes | config |
| Profit Tier 2 scale-out | +30% → sell 33% | Yes | config |
| Profit Tier 3 scale-out | +45% → sell all | Yes | config |
| Uptrend support clearance | 1% below line | No | risk_manager |
| Minimum bars for trendline exit | 6 bars | No | risk_manager |
| Go/No-Go minimum trades | 3 | No | go_no_go |
| Go/No-Go minimum days | 4 calendar days | No | go_no_go |
| Go/No-Go win rate threshold | 40% | No | go_no_go |
| Go/No-Go W/L ratio threshold | 1.5× | No | go_no_go |
| Go/No-Go profit factor threshold | 1.1 | No | go_no_go |
| Go/No-Go max drawdown threshold | 35% | No | go_no_go |
| Go/No-Go scanner age limit | 25 hours | No | go_no_go |

---

*Last updated: March 2026. This document supersedes all prior verbal descriptions of the strategy. All thresholds are as-implemented in the running system. Changes to configurable parameters take effect immediately on restart. Changes to non-configurable parameters require a code change and full backtest re-run before deployment.*
