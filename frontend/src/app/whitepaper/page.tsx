import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export const metadata = {
  title: "Foundry — Research Approach",
  description:
    "How Foundry uses LLM-assisted research and Python-first systematic testing to build and validate trading strategies.",
};

export default function WhitepaperPage() {
  return (
    <div
      className="min-h-screen"
      style={{ backgroundColor: "var(--color-nt-bg)", color: "var(--color-nt-text)" }}
    >
      {/* ── Nav ── */}
      <nav
        className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4"
        style={{
          background: "rgba(255,255,255,0.9)",
          backdropFilter: "blur(12px)",
          borderBottom: "1px solid var(--color-nt-border)",
        }}
      >
        <Link
          href="/"
          className="text-lg font-bold"
          style={{ color: "var(--color-nt-purple)", textDecoration: "none" }}
        >
          Foundry
        </Link>
        <Link
          href="/login"
          className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-opacity hover:opacity-80"
          style={{ background: "var(--color-nt-purple)", color: "#fff", textDecoration: "none" }}
        >
          Sign in
        </Link>
      </nav>

      {/* ── Article ── */}
      <main className="flex justify-center px-4 pt-28 pb-24">
        <article className="w-full max-w-2xl space-y-12">

          {/* Back link */}
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm transition-opacity hover:opacity-70"
            style={{ color: "var(--color-nt-secondary)", textDecoration: "none" }}
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Foundry
          </Link>

          {/* Title */}
          <header className="space-y-2">
            <p
              className="text-xs font-semibold uppercase tracking-widest"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              Research Approach
            </p>
            <h1
              className="text-4xl font-bold tracking-tight"
              style={{ color: "var(--color-nt-text)" }}
            >
              Foundry — Research Approach
            </h1>
            <p className="text-sm" style={{ color: "var(--color-nt-secondary)" }}>
              A conceptual overview of how strategies are built, tested, and validated on Foundry.
            </p>
          </header>

          <hr style={{ borderColor: "var(--color-nt-border)" }} />

          {/* ── Section 1: Philosophy ── */}
          <section className="space-y-4">
            <h2
              className="text-xl font-bold"
              style={{ color: "var(--color-nt-text)" }}
            >
              1. Philosophy
            </h2>
            <p
              className="text-sm leading-7"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              Durable edges in markets come from systematic research, not from black-box automation.
              We believe that language models are powerful tools for accelerating research —
              surfacing patterns, screening a large universe of candidates, and drafting testable
              hypotheses faster than a single analyst could. But acceleration is not a substitute
              for judgment.
            </p>
            <p
              className="text-sm leading-7"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              Every position taken on Foundry is the result of a human decision. The model advises;
              the human is accountable. This keeps the research loop grounded, auditable, and
              improvable over time — qualities that fully autonomous systems routinely sacrifice in
              exchange for speed.
            </p>
          </section>

          <hr style={{ borderColor: "var(--color-nt-border)" }} />

          {/* ── Section 2: The Research Loop ── */}
          <section className="space-y-4">
            <h2
              className="text-xl font-bold"
              style={{ color: "var(--color-nt-text)" }}
            >
              2. The Research Loop
            </h2>
            <p
              className="text-sm leading-7"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              Every strategy moves through a defined loop before any capital — real or paper — is
              committed to it:
            </p>
            <ol className="space-y-3 pl-1">
              {[
                {
                  step: "1",
                  title: "Human Pattern Recognition",
                  body: "Domain experts identify emerging sector themes and structural market shifts. Investment theses originate with a human.",
                },
                {
                  step: "2",
                  title: "Python Candidate Screening",
                  body: "Systematic quantitative filters screen the watchlist: volume surge detection, price structure analysis, ATR-normalised range, relative strength ranking.",
                },
                {
                  step: "3",
                  title: "LLM Hypothesis Generation",
                  body: "Language models synthesise sector research, earnings data, news flow, and technical positioning to generate directional trade hypotheses with explicit rationale.",
                },
                {
                  step: "4",
                  title: "Reinforcement Learning Validation",
                  body: "An RL model trained on historical signal outcomes continuously updates signal weights, penalising recency bias and rewarding regime-appropriate signals.",
                },
                {
                  step: "5",
                  title: "Human Final Approval",
                  body: "No position is opened without human review of the full hypothesis chain. The system surfaces; the human decides.",
                },
              ].map(({ step, title, body }) => (
                <li
                  key={step}
                  className="flex gap-4 rounded-xl p-4"
                  style={{
                    backgroundColor: "var(--color-nt-surface)",
                    border: "1px solid var(--color-nt-border)",
                  }}
                >
                  <span
                    className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold"
                    style={{
                      backgroundColor: "var(--color-nt-blue)",
                      color: "#fff",
                    }}
                  >
                    {step}
                  </span>
                  <div className="space-y-0.5">
                    <p
                      className="text-sm font-semibold"
                      style={{ color: "var(--color-nt-text)" }}
                    >
                      {title}
                    </p>
                    <p
                      className="text-sm leading-6"
                      style={{ color: "var(--color-nt-secondary)" }}
                    >
                      {body}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <hr style={{ borderColor: "var(--color-nt-border)" }} />

          {/* ── Section 3: Why Paper First ── */}
          <section className="space-y-4">
            <h2
              className="text-xl font-bold"
              style={{ color: "var(--color-nt-text)" }}
            >
              3. Why Paper First
            </h2>
            <p
              className="text-sm leading-7"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              Backtesting is a necessary condition for confidence — but it is not sufficient.
              Overfitting, look-ahead bias, and slippage assumptions can all make a strategy
              look better on historical data than it will perform in live markets. Paper trading
              is the bridge between a backtest and a real-money commitment.
            </p>
            <p
              className="text-sm leading-7"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              On Foundry, every strategy that clears backtesting enters a live paper portfolio
              tracked at market prices with realistic execution assumptions. Win rate, expectancy
              per trade, maximum drawdown, and average hold duration are all monitored continuously.
              The current live paper portfolio started at $100,000. All performance figures shown
              on the homepage reflect this paper portfolio — no real capital is at risk.
            </p>
            <p
              className="text-sm leading-7"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              Only after a meaningful paper-trading sample — enough trades to have statistical
              significance across varying market conditions — will a strategy be considered for
              live deployment.
            </p>
          </section>

          <hr style={{ borderColor: "var(--color-nt-border)" }} />

          {/* ── Section 4: Pipeline Architecture & Monitoring ── */}
          <section className="space-y-4">
            <h2
              className="text-xl font-bold"
              style={{ color: "var(--color-nt-text)" }}
            >
              4. Pipeline Architecture &amp; Monitoring
            </h2>
            <p
              className="text-sm leading-7"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              The system runs seven modular service stages in a defined sequence, each with a scoped responsibility and audit trail.
              All pipeline activity is logged with timestamps and signal chain.
              No stage can trigger trade execution without a valid watchlist entry and confirmed structure check.
            </p>
            <div className="space-y-3">
              {[
                {
                  title: "Theme Detector",
                  body: "Scans sector ETF flows, news velocity, and social signal frequency to score emerging themes (0–1 confidence).",
                },
                {
                  title: "Watchlist Builder",
                  body: "Populates the candidate pool from ETF holdings and fallback sector universes. Refresh rate: 3-hour cycle outside market hours.",
                },
                {
                  title: "Structure Checker",
                  body: "Flags candidates with clean base patterns (tight consolidation, controlled volume). Rejects extended or climactic structures.",
                },
                {
                  title: "Breakout Scanner",
                  body: "Screens for volume-confirmed price breakouts above identified resistance levels. Requires directional volume — filters panic-selling spikes.",
                },
                {
                  title: "Trade Executor",
                  body: "Submits orders via Alpaca paper API. Position sizing uses ATR-based stops with predefined risk-per-trade limits.",
                },
                {
                  title: "Risk Manager",
                  body: "Runs every 5 minutes during market hours. Enforces stop-loss execution, maximum drawdown limits, and pyramid eligibility checks.",
                },
                {
                  title: "Health Check",
                  body: "16-point system diagnostic running post-scan. Broadcasts status to owner via WhatsApp notification.",
                },
              ].map(({ title, body }) => (
                <div
                  key={title}
                  className="rounded-xl p-5 space-y-1.5"
                  style={{
                    backgroundColor: "var(--color-nt-surface)",
                    border: "1px solid var(--color-nt-border)",
                  }}
                >
                  <p
                    className="text-sm font-semibold"
                    style={{ color: "var(--color-nt-text)" }}
                  >
                    {title}
                  </p>
                  <p
                    className="text-sm leading-6"
                    style={{ color: "var(--color-nt-secondary)" }}
                  >
                    {body}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <hr style={{ borderColor: "var(--color-nt-border)" }} />

          {/* ── Section 5: Go/No-Go Protocol ── */}
          <section className="space-y-4">
            <h2
              className="text-xl font-bold"
              style={{ color: "var(--color-nt-text)" }}
            >
              5. Go/No-Go Protocol
            </h2>
            <p
              className="text-sm leading-7"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              Before transitioning from paper to live capital, the system must pass a multi-layer
              checklist. Only when all checks pass does the system flag{" "}
              <span
                className="font-mono text-xs px-1.5 py-0.5 rounded"
                style={{ backgroundColor: "var(--color-nt-surface)", border: "1px solid var(--color-nt-border)", color: "var(--color-nt-text)" }}
              >
                LIVE_READY=true
              </span>
              . Live deployment requires explicit owner action — it is never automatic.
            </p>

            {/* Technical Checks */}
            <div className="space-y-2">
              <p
                className="text-xs font-semibold uppercase tracking-widest"
                style={{ color: "var(--color-nt-secondary)" }}
              >
                Technical Checks
              </p>
              <ul className="space-y-2 pl-0">
                {[
                  "All 7 pipeline stages operational with no FAIL status in the last 7 days.",
                  "Database integrity verified — no orphaned positions, no status inconsistencies.",
                  "Notification pipeline live-tested (WhatsApp delivery confirmed).",
                  "API connectivity stable — Alpaca, Finnhub, data feeds — no degraded responses in 48h.",
                ].map((item) => (
                  <li
                    key={item}
                    className="flex gap-2.5 text-sm leading-6"
                    style={{ color: "var(--color-nt-secondary)" }}
                  >
                    <span
                      className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full"
                      style={{ backgroundColor: "var(--color-nt-blue)" }}
                    />
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            {/* Strategy Checks */}
            <div className="space-y-2">
              <p
                className="text-xs font-semibold uppercase tracking-widest"
                style={{ color: "var(--color-nt-secondary)" }}
              >
                Strategy Checks
              </p>
              <ul className="space-y-2 pl-0">
                {[
                  "Minimum 30 completed paper trades with positive expectancy.",
                  "Win rate ≥ 50% on paper capital.",
                  "Maximum drawdown on paper ≤ 8%.",
                  "Average hold time consistent with strategy thesis (2–10 days).",
                  "No single position responsible for > 40% of total return.",
                ].map((item) => (
                  <li
                    key={item}
                    className="flex gap-2.5 text-sm leading-6"
                    style={{ color: "var(--color-nt-secondary)" }}
                  >
                    <span
                      className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full"
                      style={{ backgroundColor: "var(--color-nt-blue)" }}
                    />
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            {/* Operational Checks */}
            <div className="space-y-2">
              <p
                className="text-xs font-semibold uppercase tracking-widest"
                style={{ color: "var(--color-nt-secondary)" }}
              >
                Operational Checks
              </p>
              <ul className="space-y-2 pl-0">
                {[
                  "Owner has reviewed and approved the strategy parameters.",
                  "Emergency stop (kill switch) tested and confirmed functional.",
                  "Position size limits verified against available capital.",
                  "Risk-per-trade hard cap reviewed.",
                ].map((item) => (
                  <li
                    key={item}
                    className="flex gap-2.5 text-sm leading-6"
                    style={{ color: "var(--color-nt-secondary)" }}
                  >
                    <span
                      className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full"
                      style={{ backgroundColor: "var(--color-nt-blue)" }}
                    />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <hr style={{ borderColor: "var(--color-nt-border)" }} />

          {/* ── Section 6: Strategy Principles ── */}
          <section className="space-y-4">
            <h2
              className="text-xl font-bold"
              style={{ color: "var(--color-nt-text)" }}
            >
              6. Strategy Principles
            </h2>
            <p
              className="text-sm leading-7"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              The current strategies on Foundry operate at a conceptual level around three
              principles. Specific parameters, thresholds, and entry criteria are not disclosed.
            </p>
            <div className="space-y-3">
              {[
                {
                  title: "Sector-rotation momentum",
                  body: "Strategies focus on identifying sectors where capital is actively rotating and price momentum is accelerating. The assumption is that institutional flows create multi-week trends that can be systematically identified and exploited.",
                },
                {
                  title: "Catalyst-driven entry signals",
                  body: "Entries are not made purely on technicals. A confirmable catalyst — whether macro, earnings-driven, or structural — is part of the entry thesis. This reduces the chance of entering on noise.",
                },
                {
                  title: "Conviction and volatility-based position sizing",
                  body: "Position size is a function of two inputs: the researcher's conviction in the thesis, and the recent volatility of the instrument. Higher volatility reduces position size. Higher conviction may increase it, within defined limits.",
                },
              ].map(({ title, body }) => (
                <div
                  key={title}
                  className="rounded-xl p-5 space-y-1.5"
                  style={{
                    backgroundColor: "var(--color-nt-surface)",
                    border: "1px solid var(--color-nt-border)",
                  }}
                >
                  <p
                    className="text-sm font-semibold"
                    style={{ color: "var(--color-nt-text)" }}
                  >
                    {title}
                  </p>
                  <p
                    className="text-sm leading-6"
                    style={{ color: "var(--color-nt-secondary)" }}
                  >
                    {body}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <hr style={{ borderColor: "var(--color-nt-border)" }} />

          {/* ── Section 7: What Foundry Will Offer ── */}
          <section className="space-y-4">
            <h2
              className="text-xl font-bold"
              style={{ color: "var(--color-nt-text)" }}
            >
              7. What Foundry Will Offer
            </h2>
            <p
              className="text-sm leading-7"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              The goal of Foundry is to bring research-grade infrastructure to individual traders
              who currently lack access to institutional-quality tooling. The planned platform
              includes:
            </p>
            <ul className="space-y-2 pl-0">
              {[
                "Backtesting infrastructure with walk-forward validation, built in Python and accessible through a clean interface.",
                "LLM-assisted screening that surfaces candidates and generates annotated hypotheses for human review.",
                "Human-in-the-loop execution flows — the platform is designed to support the researcher, not to trade autonomously.",
                "Performance tracking across paper and live portfolios with consistent, auditable metrics.",
              ].map((item) => (
                <li
                  key={item}
                  className="flex gap-2.5 text-sm leading-6"
                  style={{ color: "var(--color-nt-secondary)" }}
                >
                  <span
                    className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full"
                    style={{ backgroundColor: "var(--color-nt-blue)" }}
                  />
                  {item}
                </li>
              ))}
            </ul>
            <p
              className="text-sm leading-7"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              Foundry is currently in private research mode. If you want to be among the first
              to access the platform when it opens, join the waitlist.
            </p>

            {/* Waitlist CTA */}
            <div className="pt-2">
              <Link
                href="/"
                className="inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold transition-opacity hover:opacity-85"
                style={{ background: "var(--color-nt-blue)", color: "#fff", textDecoration: "none" }}
              >
                Join the waitlist
              </Link>
            </div>
          </section>

          <hr style={{ borderColor: "var(--color-nt-border)" }} />

          {/* Footer note */}
          <p
            className="text-xs"
            style={{ color: "var(--color-nt-muted)" }}
          >
            This document describes the research approach used internally at Foundry.
            It is not financial advice. All performance figures refer to paper-traded
            simulations. Past simulated performance does not guarantee future results.
          </p>
        </article>
      </main>
    </div>
  );
}
