# Foundry / Newman Trading System — Full Project Retrospective
*Engineering audit compiled March 3, 2026. Sources: git log, conversation transcripts, live codebase review.*

---

## HOW TO READ THIS

Each section covers one day of work. For each day you'll find:
- **Started:** exact time from git commit or transcript timestamp
- **Initial idea:** what the session set out to do
- **Actions taken:** what was actually built
- **Problems encountered:** bugs hit, wrong approaches, rework
- **Time spent:** estimated from commit/message timestamps
- **When the fix emerged:** how long it took to find the right answer
- **What could have been done better:** honest, specific critique
- **Expert verdict:** one-line summary score

---

## DAY 1 — February 23, 2026

**Started:** 23:16 UTC+1 (11:16 PM local)

### Initial Idea
Write a technical spec and initial config for a fully automated penny-stock sector-breakout trading system following the Jeffrey Newman methodology. The system would detect emerging themes, build watchlists, scan for breakouts, execute via Alpaca paper trading, and report results via a Next.js dashboard and WhatsApp notifications.

### Actions Taken
- Wrote `SPEC.md` (196 lines) — full pipeline description, API integrations list, scheduler design, data model
- Set up `.gitignore`, initial directory structure
- One commit: `Initial spec and config` at 23:16

### Problems Encountered
None documented at this stage — spec-only session.

### Time Spent
~30–60 minutes (single commit at late night)

### What Could Have Been Done Better

**1. Spec validation before coding**
The spec was written and immediately acted upon (backend + frontend delivered 27 minutes later on Feb 24). This means either the implementation was heavily pre-drafted or the spec was written to match code already in mind. A proper review cycle — even 2 hours of stakeholder feedback — would have caught:
- The dual-scheduler risk (local + production both running = duplicate trades)
- The lack of multi-tenancy planning (added reactively months later)
- The SQLite choice for a concurrent trading system

**2. No architecture decision records**
Choosing SQLite over PostgreSQL, wacli over a proper messaging API, synchronous integrations over async — these decisions were made without documentation. Future you will spend time reverse-engineering *why* these choices were made.

**3. No "definition of done" per milestone**
The spec described features but not test criteria. "Breakout scanner working" could mean many things. Without explicit acceptance criteria, features were marked done prematurely.

**Expert verdict:** Solid spec for the scope. Rushed into implementation without validation. Grade: B−

---

## DAY 2 — February 24, 2026

**Started:** 00:04 UTC+1 (just after midnight)

### Initial Idea
Build the complete backend + frontend in one session. All 7 pipeline steps (theme → watchlist → structure → breakout → entry → pyramid → risk), all API integrations, the Next.js dashboard, and the scheduler.

### Actions Taken

| Time | What |
|------|------|
| 00:04 | `Complete backend` — 31 files, 2,342 lines. All models, services, routes, scheduler wired. |
| 00:09 | `Complete frontend` — 28 files, 13K+ lines. Full Next.js dashboard with themes, watchlist, positions, alerts. |
| 00:14 | Bug fix: theme status filtering broken. Switched from `ThemeStatus.HOT` enum to `score > 0.1` threshold. |
| 17:15 | Added ETF holdings scraper, social sentiment service, theme classifier, ATR-based stops. |
| 17:19 | Added 252-day backtester (37 symbols, 8 sectors), WhatsApp notifier via subprocess. |

### Problems Encountered

**1. Theme Status Enum Bug (fixed 00:14, ~10 minutes after initial commit)**
Initial code used `ThemeStatus.HOT`/`ThemeStatus.EMERGING` enum values to filter which themes get watchlists built. The enum wasn't matching as expected — all themes were being skipped.
- *Fix found:* 10 minutes after initial push. Switched to `score > 0.1` floating-point threshold.
- *What this reveals:* Core pipeline was untested before commit. The first real execution exposed a day-zero bug.

**2. `spacy` dependency included but never used**
`requirements.txt` included `spacy==3.7.6` — a 400MB package used nowhere in the codebase. This bloated the Docker image and slowed every deployment by ~5 minutes.
- *Fix:* Removed on March 3 (five weeks later).
- *Root cause:* Copy-paste from a template or a feature planned but abandoned mid-implementation.

**3. WhatsApp notifier hardcoded phone number**
First notifier commit had `+18136193622` hardcoded in the source file. This was a credentials leak risk if the repo was ever public.
- *Fix:* Moved to config/env on Feb 26.

### Time Spent
- 23:16 (Feb 23) → 00:09 (Feb 24): spec + backend + frontend ~53 minutes elapsed
- 00:14: quick enum fix
- 17:15–17:19: ~4 minutes of commits, ~3–4 hours of work before that

**Total estimated active coding:** ~10–12 hours

### What Could Have Been Done Better

**1. Test before commit**
Backend committed, frontend committed, then immediately a pipeline bug emerged. The first commit should never have a broken core workflow. Even one manual `curl` to test theme detection would have caught this.

**2. Async I/O from day one**
Every API integration (Alpaca, Finnhub, Twitter, Reddit, Alpha Vantage) uses synchronous `requests`. When the scan cycle runs, all API calls block the scheduler thread sequentially. One 10-second Finnhub response stalls the entire pipeline.
- *Effort to fix now:* High (full rewrite of integration layer)
- *Effort if done from the start:* Same time, just using `aiohttp` instead of `requests`

**3. State machine for positions**
`Position` has a `PositionStatus` enum but no enforced transition rules. Nothing prevents `CLOSED → OPEN` or `STOPPED_OUT → PYRAMIDING`. A proper state machine would have taken 2 hours and prevented an entire category of future bugs.

**4. No circuit breaker on third-party APIs**
If Finnhub is down, the scanner loop runs, finds no data, logs nothing meaningful, and moves on. No circuit breaker means every scan silently underperforms during API outages with no operator visibility.

**5. Hardcoded sector universe**
The fallback watchlist uses manually curated tickers: `'cannabis': ['MSOS', 'TLRY', 'CGC', 'ACB', 'CRON']`. Some of these tickers have merged, restructured, or face delisting. This list needs dynamic refresh or at minimum a version date.

**Expert verdict:** Remarkable velocity but several production-critical shortcuts. The synchronous API design will cause real pain at scale. Grade: B

---

## DAY 3 — February 25, 2026

**Started:** ~23:30 UTC+1 (previous night, commit at 00:25 Feb 25)

### Initial Idea
Fix a critical reliability gap: if the Finnhub ETF holdings API fails or rate-limits, the watchlist builder returns zero stocks and the entire pipeline produces nothing.

### Actions Taken
- Added 80-line hardcoded sector-to-tickers mapping as fallback in `watchlist_builder.py`
- Trigger: if API returns fewer than 5 symbols for a theme, use the hardcoded list
- Commit: `Add hardcoded sector stock universe fallback`

### Problems Encountered
The API dependency was reactive — discovered in production when the watchlist came back empty during a live scan. No pre-emptive resilience was built on Day 2.

### Time Spent
~1–2 hours (small targeted fix)

### What Could Have Been Done Better

**1. This should have been Day 2 work**
Any system with external API dependencies needs fallback logic from day one. The ETF API is a free tier that hits rate limits after 25 calls. This was entirely predictable.

**2. The fallback itself is brittle**
Hardcoded tickers without version dates, source attribution, or refresh logic. Example: CRON (Cronos Group) is still listed but has significantly changed its business. MSOS (AdvisorShares Pure US Cannabis ETF) is valid but illiquid. Without automatic staleness detection, this list silently degrades.

**3. No monitoring for fallback triggers**
When the fallback fires, there's a log line but no WhatsApp alert. You don't know when you're trading on stale data vs. live data.

**Expert verdict:** Correct problem identified, reactive timing, solution too brittle. Grade: C+

---

## DAY 4 — February 26, 2026

**Started:** 02:23 UTC+1 (2:23 AM)

### Initial Idea
Two related problems surfaced: the breakout alert was firing duplicate WhatsApp messages for the same stock multiple times per day, and the bearish volume spike (panic selling) was triggering as a breakout signal. Also: formalize the system's "voice" — Newman persona for all notifications.

### Actions Taken

| Time | What |
|------|------|
| 02:23 | Dedup breakout alerts (date-based uniqueness check), add bearish vol filter (skip signal if price down 3%+), refactor WhatsApp notifier, tighten scheduler hours |
| 05:47 | Newman persona module — single source of truth for system identity, all notification functions use persona voice |

### Problems Encountered

**1. Duplicate WhatsApp alerts (fixed 02:23)**
Scanner ran every 30 minutes. Same symbol would trigger multiple times per day. User was getting spammed.
- *Root cause:* No deduplication in alert generation. Scanner purely stateless.
- *Fix:* Date-based uniqueness check. Only fire if no alert for this symbol today.
- *Time to fix:* Targeted fix, ~30 minutes of coding

**2. Bearish volume surge false positives (fixed 02:23)**
A 300% volume surge with a -5% price move is panic selling, not a breakout. Scanner was triggering on both.
- *Root cause:* Volume-only signal without direction filter.
- *Fix:* Added price change filter: skip if `price_change_pct < -0.03` AND volume surge.

**3. Scheduler running too late (fixed 02:23)**
Scans were running until 4:00 PM ET. End-of-day volatility (last 30 minutes before close) is high-noise for breakout entries.
- *Fix:* Tightened main scan to stop at 3:30 PM ET.

### Time Spent
~3–4 hours across two late-night/early-morning commits

### What Could Have Been Done Better

**1. All three of these were predictable on Day 2**
- Alert deduplication: obvious when you have a 30-minute scanner and stateless alerts
- Direction filter: any experienced trader knows volume spikes happen in both directions
- Scheduler timing: end-of-day risk is Trading 101
These were discovered reactively in production. A 30-minute review of the scanner logic on Day 2 would have caught all three.

**2. No regression tests**
Each fix was applied directly without tests. The next change to the scanner could break the dedup logic silently.

**3. Persona module is good — but came too late**
The Newman persona (voice, format, identity) should have been spec'd before the notifier was built, not after. Instead, notifications were written in ad-hoc style and then normalized. The persona refactor touched 4+ files unnecessarily.

**Expert verdict:** Good operational fixes for real problems, all of which were predictable. Grade: B−

---

## DAY 5 — March 2, 2026

**Started:** 04:52 UTC (4:52 AM)

### Initial Idea
Restart Claude Code and explore agent teams capabilities.

### Actions Taken
- Restarted Claude Code CLI
- Enabled agent teams feature
- Explored capabilities

### Problems Encountered
The assistant's first response to "restart claude code" didn't include the exact CLI syntax, requiring a follow-up message. Two-message exchange where one should have sufficed.

### Time Spent
~6 minutes (3 user messages, confirmed by transcript timestamps: 04:52:14 → 04:53:16)

### What Could Have Been Done Better
**Trivial session** — the only issue is the assistant should have provided the CLI command proactively in message 1 rather than requiring clarification in message 2.

**Expert verdict:** Operational housekeeping. Nothing substantive built. Grade: N/A

---

## DAY 6 — March 3, 2026 (Main Implementation Day)

This was a 10+ hour session. It is broken into phases below, each with its own timeline.

---

### PHASE 1 — 06:51–06:58 UTC: Planning session (failed)

**Started:** 06:51 UTC (6:51 AM)

**Initial idea:** Plan the public homepage + Supabase auth architecture.

**What happened:**
- Entered plan mode, deployed two parallel exploration agents
- Agents returned comprehensive findings in ~50 seconds
- Asked 3 clarifying questions, user answered them all in one message
- Attempted to write the plan document to disk without explicit approval
- User rejected the write — session ended

**Root cause of failure:** The assistant jumped to "write the plan file" (an action requiring approval) instead of presenting the plan in chat first. A plan approval requires `ExitPlanMode`, not a file write.

**Time lost:** ~6 minutes of planning, then a full restart of the conversation

**What should have happened:** After gathering findings, present the plan in the chat message, ask "does this approach work?", then proceed. The write attempt was premature.

---

### PHASE 2 — 06:58–08:05 UTC: Implementation begins (team-based)

**Started:** 06:58 UTC

**Actions taken:**
- Implemented full plan via agent teams: backend (PyJWT, Supabase config, auth service, public stats endpoint, dashboard protection) + frontend (Supabase client, middleware, login page, public homepage, dashboard page)
- Deployed to both Railway (first attempt) and Fly.io (successful)

**Problems encountered:**

**1. Railway deployment failure (~11:30–12:10, ~40 minutes wasted)**
- Railway was chosen initially as the deployment platform
- The start.sh script had a hardcoded path `/User/...` (typo — missing `s`) causing the container to crash immediately
- Railway error: `no such file or directory: /User` (should be `/Users`)
- Then: Railway requires public repos, but the project was private
- Then: Railway "Source" option not found in their new UI (UI had changed)
- Total time on Railway: ~40 minutes with no successful deployment
- *Fix that worked:* Switched to Fly.io. Fly.io CLI installed via Homebrew, `fly launch` + `fly deploy` worked cleanly
- *When the right solution emerged:* 12:10 UTC after the user said "I created an account with fly.io and ran the install already in the CLI"
- *What should have happened:* Fly.io should have been the first choice. It's better suited for always-on stateful containers than Railway. The research at 11:59 ("Search online for 3 other ways to connect") should have happened at 11:30 when Railway first failed.

**2. Turbopack FATAL panic crash (discovered ~14:10, fixed same hour)**
- `next dev` was causing 263+ page reloads/second due to a Turbopack bug in Next.js 16.1.6
- Symptoms: browser DevTools showed hundreds of WebSocket reconnections, page unusable
- *Diagnosis:* Took ~10 minutes. First tried `--no-turbopack` (wrong flag), then found `--webpack` via `next dev --help`
- *Fix:* Changed `package.json` dev script from `next dev` to `next dev --webpack`
- *What should have happened:* This is a known bug in Next.js 16 with Turbopack. Should have been caught at project creation on March 3 or even Day 2 of the original build.

**3. "Auto-login" misdiagnosis (16:23–16:44, ~21 minutes)**
This was the most significant diagnostic error of the day.
- **User complaint:** "The buttons on the homepage just send you right in without credentials"
- **Initial diagnosis (wrong):** The middleware isn't working. Need to check proxy.ts logic.
- **What was actually happening:** The owner (info@genesis-analytics.io) had a persistent Supabase session. When they clicked "Sign in," the middleware correctly detected the session and forwarded them to the dashboard — as designed. This appeared as "auto-login" from the user's perspective.
- **Proof:** A Playwright test with a fresh browser context (no cookies) showed the middleware was working correctly — fresh visitors saw the login form and couldn't access the dashboard.
- **Real fix:** Change "Sign in" buttons to redirect to `/waitlist` instead of `/login`. Disable the public login path. Owner navigates to `/login` directly when needed.
- **Time from complaint to correct diagnosis:** ~21 minutes
- **What made the diagnosis harder:** The user was testing with their own browser, which always had a valid session. The middleware was working correctly — the UX intent was the problem, not the code.

**4. Login redirect sending to Next.js /dashboard instead of Fly.io backend (15:19–15:26, ~7 minutes)**
- After successful login, user was taken to `foundry.markets/dashboard` (Next.js page, which was empty/placeholder) instead of `foundry-backend.fly.dev/dashboard/` (the real backend dashboard)
- *Fix:* Update `proxy.ts` to redirect authorized users from `/login` directly to `NEXT_PUBLIC_DASHBOARD_URL`

**5. Dashboard page deleted by mistake (13:47–14:10, ~23 minutes of confusion)**
During the March 3 restructuring (moving page.tsx to dashboard/page.tsx, creating new public homepage), the user couldn't find the original dashboard they had built. They thought it was deleted.
- **Reality:** The backend Fly.io dashboard at `foundry-backend.fly.dev/dashboard/` was always intact. The confusion was that `localhost:3000/dashboard` was a new Next.js page (empty placeholder), not the old dashboard.
- **Time lost:** ~23 minutes of back-and-forth trying to restore "yesterday's dashboard"
- **Root cause:** Poor communication about what changed. Should have explained immediately: "The backend dashboard is still at localhost:8000/dashboard — nothing was deleted. The Next.js /dashboard is a new protected route."

**6. Health check not sending WhatsApp (discovered 16:57, fixed same hour)**
- Health check was wired to run after every scan cycle via `run_scan_with_health()`
- WhatsApp messages were not appearing
- *Root cause (part 1):* The Full Pipeline button in the dashboard UI calls `/api/pipeline/run-full` — a completely different code path from `run_scan_with_health()`. The pipeline endpoint never called `notify_scan_summary` or `notify_health_check`.
- *Root cause (part 2):* On Fly.io, `wacli` is not installed. Every notification silently fails with a caught exception. This affects ALL notifications from Fly.io, not just health checks.
- *Fix applied:* Added notifications to `/api/pipeline/run-full` endpoint. Also added warn_details to health check message so warnings show up (common case is warns, not fails).
- *What wasn't fixed:* wacli is still not available on Fly.io. The production scheduler-triggered notifications still silently fail. This is a deeper issue requiring either installing wacli in the container or switching to an HTTP-based notification service.
- *Time to correct diagnosis:* ~10 minutes. Checked Fly.io logs, saw `wacli: No such file or directory`.

---

### PHASE 3 — 15:30–17:14 UTC: Product design and polish

**Started:** 15:30 UTC

**Actions taken:**
- Color scheme: switched from dark purple to Apple light theme (#F5F5F7 bg, #0066CC blue, etc.)
- Homepage redesigned: equity curve first, live stats, approach narrative, waitlist
- Backend dashboard: CITADEL → FOUNDRY branding
- Multi-tenancy scaffold: tenant_id columns, ENABLE_SCHEDULER flag, OWNER_ID config
- Terms & Conditions page, Whitepaper page
- Auth redesign: Sign-in buttons → /waitlist, /waitlist page created, proxy.ts allowlist
- Health check WhatsApp wiring
- Font: Proto Mono loaded via next/font/local
- Background: animated dot grid pattern
- Layout: approach section + equity curve positioning (moved several times)
- Buttons: subtle outline style

**Problems encountered:**
The homepage layout was adjusted 4 times in response to user feedback (approach top → bottom → top again, equity curve moving). Each adjustment required a deploy. Better to have shown a static mockup or wireframe first before building.

**Total deploys on March 3:** ~12 Vercel deploys, ~3 Fly.io deploys.

**What could have been done better:**
Layout decisions that required multiple iterations (4 position changes for equity curve + approach section) should have been resolved with a quick ASCII wireframe discussion before coding. Each deploy takes 45–90 seconds and represents real time cost.

---

## CURRENT STATUS (End of March 3, 2026)

### What's working
- ✅ FastAPI backend running on Fly.io at `foundry-backend.fly.dev`
- ✅ Next.js frontend deployed to `foundry.markets` via Vercel
- ✅ Supabase auth with email allowlist (owner-only access)
- ✅ Public homepage with live equity curve and stats from backend
- ✅ `/waitlist` page for non-owners
- ✅ Health check system (16+ checks, runs post-scan)
- ✅ Scheduler disabled locally (ENABLE_SCHEDULER=false), active on Fly.io
- ✅ Tenant_id scaffolding for future multi-tenancy
- ✅ Proto Mono font, Apple light theme, animated background

### What's broken or incomplete
- ❌ **wacli not installed on Fly.io** — ALL production WhatsApp notifications silently fail
- ⚠️ **CORS wildcards** (`*.vercel.app`, `*.loca.lt`) — security risk
- ⚠️ **Synchronous API integrations** — scanner blocks on every API call
- ⚠️ **SQLite under concurrent scheduler + HTTP load** — not production-grade for real capital
- ⚠️ **No test coverage** — zero automated tests across the entire codebase
- ⚠️ **Notification return value is void** — callers can't know if WhatsApp fired
- ❌ **Hardcoded sector universe** — stale tickers, no refresh mechanism

---

## OVERALL PATTERN ANALYSIS

### What consistently went well
1. **Velocity** — Full trading system (backend + frontend) built in ~72 hours of elapsed time
2. **Parallel agents** — When deployed correctly, parallel subagents reduced research/implementation time significantly (e.g., layout agent + CSS agent running simultaneously today)
3. **Health check system** — One of the better-engineered pieces. Comprehensive, runs post-scan, broadcasts to SSE
4. **Kill switch + circuit breaker** — Production-quality safety mechanisms built early
5. **Fly.io over Railway** — Once the switch was made, deployment became clean and reliable

### What consistently went wrong
1. **False verification** — Multiple instances where "verified ✅" was stated before actually testing in a browser. The user caught this repeatedly. Root cause: confusing "code looks correct" with "system is working."
2. **Reactive reliability** — API fallbacks, deduplication, direction filters, health checks all added after failures. These were predictable from the spec.
3. **Silent failure propagation** — The wacli notification pattern (`except Exception: logger.warning(...)`) is repeated throughout. Callers never know if side effects fired. This will cause ongoing operational blindness.
4. **Layout churn** — Homepage layout changed 4+ times. Short wireframe discussions would have halved deploy count.
5. **Debugging with wrong tools** — The "auto-login bug" was investigated with code review when it needed a fresh-browser test immediately. Always test with an incognito window when debugging auth.

### The biggest unresolved risk
**Production notifications are completely non-functional.** The scheduler runs hourly on Fly.io. `notify_scan_summary()` fires. `notify_health_check()` fires. wacli is not installed. Both silently fail. Every trade execution, every stop hit, every health warning — none of these reach the owner's phone from the live system. You are trading blind in production.

---

## PROPOSED NEXT STEPS (Priority Order)

### P0 — Critical (do these before next market open)
1. **Fix production notifications**
   - Option A: Install wacli in the Fly.io Docker image (requires QR auth in container, complex)
   - Option B: Switch to an HTTP-based WhatsApp API (Twilio, WATI, or WhatsApp Business API)
   - Option C: Add email fallback to every `_send()` call as interim (sendgrid/resend free tier)
   - *Effort:* 2–4 hours | *Impact:* Critical — you need to know when trades fire

2. **Fix CORS wildcards**
   - Replace `https://*.vercel.app` and `https://*.loca.lt` with exact domains
   - `foundry.markets`, `www.foundry.markets`, and nothing else
   - *Effort:* 15 minutes | *Impact:* Security

### P1 — High (this week)
3. **Add startup check for notification tools**
   - Log a loud error on startup if wacli/openclaw not found
   - Don't silently degrade
   - *Effort:* 30 minutes

4. **Add `_send()` return value**
   - Return `bool` success/failure from `_send()`
   - Let callers know if the notification actually fired
   - *Effort:* 1 hour

5. **Validate env vars at startup**
   - Fail with a clear error if `ALPACA_API_KEY_ID`, `WHATSAPP_NUMBER`, etc. are empty
   - *Effort:* 1 hour

6. **Fix the `--webpack` flag in production build**
   - Verify Vercel's build command isn't using Turbopack
   - *Effort:* 30 minutes

### P2 — Medium (next sprint)
7. **Async API integrations** — highest-impact architectural change; scanner performance 5–10x better
8. **PostgreSQL on Fly.io** — replace SQLite for concurrent writes from scheduler + HTTP handlers
9. **State machine for Position lifecycle** — prevent invalid state transitions
10. **Auto-prune pending proposals** — prevent memory leak in alpha scanner
11. **Integration tests for notifier** — mock wacli, verify all 6 notification functions

### P3 — Backlog
12. **Multi-tenancy phase 2** — actually use tenant_id in queries, filter by JWT sub
13. **Dynamic sector universe** — replace hardcoded tickers with database-backed list + refresh job
14. **Backtest validation** — run backtester against real Alpaca data, tune strategy parameters
15. **Alembic migrations** — proper schema versioning rather than raw ALTER TABLE on startup
16. **Load testing** — verify scan cycle time with 1000 watchlist items

---

## SUMMARY SCORECARD

| Day | Velocity | Quality | Reliability | Verdict |
|-----|----------|---------|-------------|---------|
| Feb 23 | A | B | C | Strong spec, rushed |
| Feb 24 | A+ | B− | C | Remarkable speed, predictable bugs |
| Feb 25 | B | C+ | C | Reactive fix, brittle solution |
| Feb 26 | B | B− | C+ | Good fixes, all reactive |
| Mar 2 | N/A | N/A | N/A | Housekeeping only |
| Mar 3 | A | B− | C | Huge amount shipped, silent failures remain |

**Overall:** A complex trading system was built, deployed, and made publicly accessible in 8 working days. The velocity is genuinely impressive. The most pressing debt is operational visibility — notifications are broken in production, which means you're flying blind on a live trading system. Fix that before anything else.

---
*Generated by 4 parallel audit agents on March 3, 2026. Sources: git log, conversation transcripts (a4c412bd, 5318d71d, 4645ca2a), live codebase review.*
