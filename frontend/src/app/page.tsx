"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  TrendingUp,
  Activity,
  Clock,
  BarChart2,
  Layers,
  ArrowRight,
  FlaskConical,
  BrainCircuit,
} from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

interface PublicStats {
  total_closed_trades: number;
  win_rate_pct: number;
  avg_hold_days: number;
  total_realized_pnl_pct: number;
  open_positions: number;
  system_status: string;
  trading_mode: "paper" | "live" | "paused";
  est_time: string;
}

interface EquityPoint {
  label: string;
  value: number;
}

interface EquityCurvePoint {
  date: string;
  equity_pct: number;
}

interface EquityCurveResponse {
  data_points: EquityCurvePoint[];
  last_updated: string;
}

interface MetricsResponse {
  equity_curve: EquityPoint[];
  portfolio_value: number;
}

interface SummaryResponse {
  summary: string;
  generated_at: string;
  cached: boolean;
}

// ── Backtest results (from 5-year daily backtest, March 2 2026) ──────────────

const BACKTEST_STATS = {
  total_trades: 205,
  win_rate_pct: 35.6,
  avg_hold_days: 4.2,
  total_return_pct: 233.8,
  expectancy_per_trade: 12.1,
  profit_factor: 2.62,
  max_drawdown_pct: 7.0,
  win_loss_ratio: 4.73,
  period: "5yr daily (2021–2026)",
  split: "Out-of-sample from 2024",
};

const backtestStatItems = () => [
  {
    label: "Win Rate",
    value: `${BACKTEST_STATS.win_rate_pct}%`,
    positive: BACKTEST_STATS.win_rate_pct >= 50,
    icon: TrendingUp,
  },
  {
    label: "Total Return",
    value: `+${BACKTEST_STATS.total_return_pct}%`,
    positive: true,
    icon: BarChart2,
  },
  {
    label: "Max Drawdown",
    value: `-${BACKTEST_STATS.max_drawdown_pct}%`,
    positive: null,
    icon: Clock,
  },
  {
    label: "Total Trades",
    value: BACKTEST_STATS.total_trades.toString(),
    positive: null,
    icon: Activity,
  },
  {
    label: "Profit Factor",
    value: `${BACKTEST_STATS.profit_factor}x`,
    positive: BACKTEST_STATS.profit_factor >= 1,
    icon: Layers,
  },
];

// ── Stat item definitions ────────────────────────────────────────────────────

const statItems = (stats: PublicStats) => [
  {
    label: "Win Rate",
    value: `${stats.win_rate_pct.toFixed(1)}%`,
    positive: stats.win_rate_pct >= 50,
    icon: TrendingUp,
  },
  {
    label: "Total Return",
    value: `${stats.total_realized_pnl_pct >= 0 ? "+" : ""}${stats.total_realized_pnl_pct.toFixed(1)}%`,
    positive: stats.total_realized_pnl_pct >= 0,
    icon: BarChart2,
  },
  {
    label: "Avg Hold",
    value: `${stats.avg_hold_days.toFixed(1)}d`,
    positive: null,
    icon: Clock,
  },
  {
    label: "Closed Trades",
    value: stats.total_closed_trades.toString(),
    positive: null,
    icon: Activity,
  },
  {
    label: "Open Positions",
    value: stats.open_positions.toString(),
    positive: null,
    icon: Layers,
  },
];

// ── Y-axis / tooltip formatters ───────────────────────────────────────────────

function fmtDollar(v: number) {
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

// ── Custom tooltip for equity curve ──────────────────────────────────────────

function EquityTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const v = payload[0].value;
  const formatted = `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs shadow-md"
      style={{
        background: "var(--color-nt-surface)",
        border: "1px solid var(--color-nt-border)",
        color: "var(--color-nt-text)",
      }}
    >
      <p style={{ color: "var(--color-nt-secondary)" }} className="mb-0.5">{label}</p>
      <p className="font-semibold tabular-nums">{formatted}</p>
    </div>
  );
}

function fmtPct(v: number) {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

// ── Main component ────────────────────────────────────────────────────────────

export default function HomePage() {
  const router = useRouter();
  // Public stats
  const [stats, setStats] = useState<PublicStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsUpdateKey, setStatsUpdateKey] = useState(0);

  // Equity curve from /api/public/equity-curve
  const [equityCurveData, setEquityCurveData] = useState<EquityCurvePoint[]>([]);
  const [equityCurveLoading, setEquityCurveLoading] = useState(true);

  // Legacy equity curve + portfolio value (from dashboard/api/metrics, kept for portfolio value)
  const [portfolioValue, setPortfolioValue] = useState<number | null>(null);

  // LLM summary
  const [summaryText, setSummaryText] = useState<string>("");
  const [summaryAge, setSummaryAge] = useState<string>("");

  // Performance tab
  type PerfTab = "backtesting" | "paper" | "live";
  const [perfTab, setPerfTab] = useState<PerfTab>("paper");

  // Waitlist form
  const [email, setEmail] = useState("");
  const [waitlistSubmitted, setWaitlistSubmitted] = useState(false);

  // ── Fetch helpers ─────────────────────────────────────────────────────────

  const fetchStats = () => {
    fetch(`/backend/api/public/stats`)
      .then((r) => r.json())
      .then((data: PublicStats) => {
        setStats(data);
        setStatsUpdateKey((k) => k + 1);
      })
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));
  };

  const fetchEquityCurve = () => {
    fetch(`/backend/api/public/equity-curve`)
      .then((r) => r.json())
      .then((data: EquityCurveResponse) => {
        if (Array.isArray(data.data_points)) setEquityCurveData(data.data_points);
      })
      .catch(() => {})
      .finally(() => setEquityCurveLoading(false));
  };

  const fetchSummary = () => {
    fetch(`/backend/api/public/summary`)
      .then((r) => r.json())
      .then((data: SummaryResponse) => {
        setSummaryText(data.summary || "");
        if (data.generated_at) {
          const d = new Date(data.generated_at);
          const now = new Date();
          const diffMin = Math.round((now.getTime() - d.getTime()) / 60000);
          if (diffMin < 1) setSummaryAge("just now");
          else if (diffMin < 60) setSummaryAge(`${diffMin}m ago`);
          else setSummaryAge(`${Math.round(diffMin / 60)}h ago`);
        }
      })
      .catch(() => {});
  };

  // ── On-mount fetches ──────────────────────────────────────────────────────

  useEffect(() => {
    fetchStats();
    fetchEquityCurve();
    fetchSummary();

    // Legacy metrics for portfolio value
    fetch(`/backend/dashboard/api/metrics`)
      .then((r) => r.json())
      .then((data: MetricsResponse) => {
        if (typeof data.portfolio_value === "number") setPortfolioValue(data.portfolio_value);
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Polling: stats every 30 seconds ──────────────────────────────────────

  useEffect(() => {
    const id = setInterval(fetchStats, 30000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Polling: equity curve + summary every 15 minutes ─────────────────────

  useEffect(() => {
    const id = setInterval(() => {
      fetchEquityCurve();
      fetchSummary();
    }, 900000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const statusColor =
    stats?.system_status === "running"
      ? "var(--color-nt-green)"
      : stats?.system_status === "paused"
      ? "var(--color-nt-amber)"
      : "var(--color-nt-muted)";

  const tradingMode = stats?.trading_mode ?? "paper";
  const tradingModeBadgeColor =
    tradingMode === "live" ? "#22C55E" : tradingMode === "paused" ? "#EF4444" : "#F59E0B";
  const pulseColor =
    tradingMode === "live" ? "bg-green-500" : tradingMode === "paused" ? "bg-red-500" : "bg-amber-500";

  const portfolioChange =
    portfolioValue !== null ? portfolioValue - 100000 : null;
  const portfolioChangePct =
    portfolioChange !== null ? (portfolioChange / 100000) * 100 : null;

  function handleWaitlist(e: React.FormEvent) {
    e.preventDefault();
    setWaitlistSubmitted(true);
  }

  return (
    <div
      className="min-h-screen bg-dot-pattern"
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
          className="text-sm font-semibold"
          style={{ color: "#AEAEB2", textDecoration: "none" }}
        >
          Foundry
        </Link>
        <div className="flex items-center gap-4">
          <Link
            href="/whitepaper"
            className="text-sm"
            style={{ color: "var(--color-nt-secondary)", textDecoration: "none" }}
          >
            Whitepaper
          </Link>
          <button
            onClick={() => router.push("/waitlist")}
            className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors hover:bg-black/5"
            style={{ color: "var(--color-nt-secondary)", border: "1px solid var(--color-nt-border)" }}
          >
            Sign in
          </button>
        </div>
      </nav>

      {/* ── Main content ── */}
      <main className="flex flex-col items-center px-4 pt-28 pb-20">
        <div className="w-full max-w-2xl space-y-10">

          {/* ── Hero header ── */}
          <div className="space-y-3 pt-4">
            <h1
              className="text-2xl font-semibold leading-snug tracking-tight"
              style={{ color: "var(--color-nt-text)" }}
            >
              A research loop for equity strategy.
            </h1>
            <p className="text-sm leading-relaxed max-w-lg" style={{ color: "var(--color-nt-secondary)" }}>
              A human generates the trade theses, and the language model writes the research hypotheses. Python validates them against price structure systematically.
            </p>
            <p className="text-xs" style={{ color: "var(--color-nt-muted)" }}>
              Paper trading under strict risk management and security protocols. Live deployment requires passing all go/no-go checks.
            </p>
          </div>

          {/* ── Equity Curve card ── */}
          <Card
            style={{
              backgroundColor: "var(--color-nt-surface)",
              borderColor: "var(--color-nt-border)",
            }}
          >
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <CardTitle
                    className="text-sm font-medium"
                    style={{ color: "var(--color-nt-secondary)" }}
                  >
                    Current results are
                  </CardTitle>
                  <span
                    className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wider"
                    style={{
                      color: tradingModeBadgeColor,
                      background: `color-mix(in srgb, ${tradingModeBadgeColor} 12%, transparent)`,
                      border: `1px solid color-mix(in srgb, ${tradingModeBadgeColor} 30%, transparent)`,
                    }}
                  >
                    {tradingMode}
                  </span>
                </div>
                {stats?.est_time && (
                  <span className="text-xs tabular-nums" style={{ color: "var(--color-nt-muted)" }}>
                    {stats.est_time}
                  </span>
                )}
              </div>
              {portfolioValue !== null && (
                <div className="mt-2">
                  <p
                    className="tabular-nums text-xl font-bold"
                    style={{ color: "var(--color-nt-text)" }}
                  >
                    {fmtDollar(portfolioValue)}
                  </p>
                  {portfolioChangePct !== null && (
                    <p
                      className="tabular-nums text-xs font-semibold"
                      style={{
                        color:
                          portfolioChangePct >= 0
                            ? "var(--color-nt-green)"
                            : "var(--color-nt-red)",
                      }}
                    >
                      {portfolioChangePct >= 0 ? "+" : ""}
                      {portfolioChangePct.toFixed(2)}% from $100,000
                    </p>
                  )}
                </div>
              )}
            </CardHeader>
            <CardContent>
              {equityCurveLoading ? (
                <div className="skeleton h-52 rounded-lg" />
              ) : equityCurveData.length === 0 ? (
                <p
                  className="py-8 text-center text-sm"
                  style={{ color: "var(--color-nt-muted)" }}
                >
                  Accumulating data...
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={210}>
                  <LineChart
                    data={equityCurveData.map((p) => ({ label: p.date, value: p.equity_pct }))}
                    margin={{ top: 4, right: 8, bottom: 0, left: 8 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="var(--color-nt-border)"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 10, fill: "var(--color-nt-secondary)" }}
                      tickLine={false}
                      axisLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tickFormatter={fmtPct}
                      tick={{ fontSize: 10, fill: "var(--color-nt-secondary)" }}
                      tickLine={false}
                      axisLine={false}
                      width={56}
                      domain={["auto", "auto"]}
                    />
                    <Tooltip content={<EquityTooltip />} />
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="var(--color-nt-blue)"
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
              <p
                className="mt-3 text-xs italic"
                style={{ color: "var(--color-nt-secondary)" }}
              >
                Starting portfolio: $100,000. All results are paper-traded simulations.
              </p>
            </CardContent>
          </Card>

          {/* ── Waitlist (primary CTA) ── */}
          <div
            className="rounded-2xl p-8 text-center space-y-4"
            style={{
              backgroundColor: "var(--color-nt-surface)",
              border: "1px solid var(--color-nt-border)",
            }}
          >
            <h2
              className="text-xl font-bold"
              style={{ color: "var(--color-nt-text)" }}
            >
              Join the waitlist
            </h2>
            <p className="text-sm" style={{ color: "var(--color-nt-secondary)" }}>
              Be among the first to run your own strategy on the Foundry platform.
            </p>
            {waitlistSubmitted ? (
              <p
                className="animate-fade-in text-sm font-semibold"
                style={{ color: "var(--color-nt-green)" }}
              >
                Thanks, you&apos;re on the list!
              </p>
            ) : (
              <form
                onSubmit={handleWaitlist}
                className="flex flex-col sm:flex-row gap-3 justify-center"
              >
                <input
                  type="email"
                  required
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="flex-1 max-w-xs rounded-lg px-4 py-2.5 text-sm outline-none"
                  style={{
                    backgroundColor: "var(--color-nt-elevated)",
                    border: "1px solid var(--color-nt-border)",
                    color: "var(--color-nt-text)",
                  }}
                />
                <button
                  type="submit"
                  className="rounded-lg px-5 py-2.5 text-sm font-medium transition-opacity hover:opacity-70"
                  style={{ background: "none", border: "1px solid var(--color-nt-blue)", color: "var(--color-nt-blue)" }}
                >
                  Request access
                </button>
              </form>
            )}
          </div>

          {/* ── Section divider ── */}
          <div
            className="w-full"
            style={{ height: "1px", backgroundColor: "var(--color-nt-border)", opacity: 0.5 }}
          />

          {/* ── Live stats card ── */}
          <Card
            style={{
              backgroundColor: "var(--color-nt-surface)",
              borderColor: "var(--color-nt-border)",
            }}
          >
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span
                    className={`inline-block w-2 h-2 rounded-full animate-pulse ${pulseColor}`}
                  />
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => setPerfTab("backtesting")}
                      className="text-[11px] font-medium tracking-wide transition-all"
                      style={{
                        color: perfTab === "backtesting" ? "var(--color-nt-text)" : "var(--color-nt-muted)",
                        opacity: perfTab === "backtesting" ? 1 : 0.4,
                        backgroundColor: perfTab === "backtesting" ? "rgba(255, 230, 0, 0.35)" : "transparent",
                        padding: "1px 6px",
                        borderRadius: "3px",
                        border: "none",
                        cursor: "pointer",
                      }}
                    >
                      Backtesting
                    </button>
                    <span className="text-[10px]" style={{ color: "var(--color-nt-muted)", opacity: 0.3 }}>
                      /
                    </span>
                    <button
                      onClick={() => setPerfTab("paper")}
                      className="text-[11px] font-medium tracking-wide transition-all"
                      style={{
                        color: perfTab === "paper" ? "var(--color-nt-text)" : "var(--color-nt-muted)",
                        opacity: perfTab === "paper" ? 1 : 0.4,
                        backgroundColor: perfTab === "paper" ? "rgba(255, 230, 0, 0.35)" : "transparent",
                        padding: "1px 6px",
                        borderRadius: "3px",
                        border: "none",
                        cursor: "pointer",
                      }}
                    >
                      Paper Trading
                    </button>
                    <span className="text-[10px]" style={{ color: "var(--color-nt-muted)", opacity: 0.3 }}>
                      /
                    </span>
                    <span
                      className="text-[11px] font-medium tracking-wide"
                      style={{ color: "var(--color-nt-muted)", opacity: 0.25, cursor: "default" }}
                    >
                      Live
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {stats && (
                    <span
                      className="inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-semibold uppercase tracking-widest"
                      style={{
                        color: statusColor,
                        background: `color-mix(in srgb, ${statusColor} 15%, transparent)`,
                        border: `1px solid color-mix(in srgb, ${statusColor} 30%, transparent)`,
                      }}
                    >
                      {stats.system_status}
                    </span>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {perfTab === "paper" ? (
                <>
                  {statsLoading ? (
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                      {[...Array(5)].map((_, i) => (
                        <div key={i} className="skeleton h-20 rounded-lg" />
                      ))}
                    </div>
                  ) : !stats ? (
                    <p className="py-4 text-center text-sm" style={{ color: "var(--color-nt-muted)" }}>
                      Stats unavailable
                    </p>
                  ) : (
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                      {statItems(stats).map(({ label, value, positive, icon: Icon }) => (
                        <div
                          key={label}
                          className="card-glow rounded-lg p-4"
                          style={{
                            backgroundColor: "var(--color-nt-elevated)",
                            border: "1px solid var(--color-nt-border)",
                          }}
                        >
                          <div className="mb-2 flex items-center gap-1.5">
                            <Icon
                              className="h-3.5 w-3.5"
                              style={{ color: "var(--color-nt-muted)" }}
                            />
                            <span
                              className="text-xs font-medium"
                              style={{ color: "var(--color-nt-secondary)" }}
                            >
                              {label}
                            </span>
                          </div>
                          <span
                            key={`${label}-${statsUpdateKey}`}
                            className="animate-fade-in tabular-nums text-2xl font-bold"
                            style={{
                              color:
                                positive === null
                                  ? "var(--color-nt-text)"
                                  : positive
                                  ? "var(--color-nt-green)"
                                  : "var(--color-nt-red)",
                            }}
                          >
                            {value}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* ── LLM daily summary ── */}
                  {(summaryText || summaryAge) && (
                    <div
                      className="mt-4 rounded-lg p-4"
                      style={{
                        backgroundColor: "var(--color-nt-elevated)",
                        border: "1px solid var(--color-nt-border)",
                      }}
                    >
                      <p
                        className="text-xs font-medium uppercase tracking-widest mb-2"
                        style={{ color: "var(--color-nt-muted)" }}
                      >
                        Today&apos;s Summary
                      </p>
                      <p
                        className="text-sm leading-relaxed"
                        style={{ color: "var(--color-nt-secondary)" }}
                      >
                        {summaryText || "Generating summary..."}
                      </p>
                      {summaryAge && (
                        <p
                          className="text-xs mt-1"
                          style={{ color: "var(--color-nt-muted)" }}
                        >
                          Updated {summaryAge}
                        </p>
                      )}
                    </div>
                  )}
                </>
              ) : perfTab === "backtesting" ? (
                <>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    {backtestStatItems().map(({ label, value, positive, icon: Icon }) => (
                      <div
                        key={label}
                        className="card-glow rounded-lg p-4"
                        style={{
                          backgroundColor: "var(--color-nt-elevated)",
                          border: "1px solid var(--color-nt-border)",
                        }}
                      >
                        <div className="mb-2 flex items-center gap-1.5">
                          <Icon
                            className="h-3.5 w-3.5"
                            style={{ color: "var(--color-nt-muted)" }}
                          />
                          <span
                            className="text-xs font-medium"
                            style={{ color: "var(--color-nt-secondary)" }}
                          >
                            {label}
                          </span>
                        </div>
                        <span
                          className="animate-fade-in tabular-nums text-2xl font-bold"
                          style={{
                            color:
                              positive === null
                                ? "var(--color-nt-text)"
                                : positive
                                ? "var(--color-nt-green)"
                                : "var(--color-nt-red)",
                          }}
                        >
                          {value}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div
                    className="mt-4 rounded-lg p-4"
                    style={{
                      backgroundColor: "var(--color-nt-elevated)",
                      border: "1px solid var(--color-nt-border)",
                    }}
                  >
                    <p
                      className="text-xs font-medium uppercase tracking-widest mb-2"
                      style={{ color: "var(--color-nt-muted)" }}
                    >
                      Backtest Parameters
                    </p>
                    <p
                      className="text-sm leading-relaxed"
                      style={{ color: "var(--color-nt-secondary)" }}
                    >
                      {BACKTEST_STATS.period} · Out-of-sample from 2024 · 0.75% slippage per fill · SPY bull-regime gate · Survivorship bias noted
                    </p>
                  </div>
                </>
              ) : (
                <p className="py-8 text-center text-sm" style={{ color: "var(--color-nt-muted)" }}>
                  Live trading not yet active. Pending go/no-go checks.
                </p>
              )}
            </CardContent>
          </Card>

          {/* ── The Approach ── */}
          <section className="space-y-4">
            <h2
              className="text-xs font-semibold uppercase tracking-widest"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              The Approach
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {/* Card 1 — Human Strategy */}
              <div
                className="rounded-xl p-5 space-y-2"
                style={{
                  backgroundColor: "var(--color-nt-surface)",
                  border: "1px solid var(--color-nt-border)",
                }}
              >
                <div className="flex items-center gap-2">
                  <BrainCircuit
                    className="h-4 w-4 flex-shrink-0"
                    style={{ color: "var(--color-nt-blue)" }}
                  />
                  <span className="text-sm font-semibold" style={{ color: "var(--color-nt-text)" }}>
                    Human Strategy
                  </span>
                </div>
                <p className="text-sm leading-relaxed" style={{ color: "var(--color-nt-secondary)" }}>
                  A human designs the strategy, writes the Python code, and makes all final entry decisions. The system surfaces candidates; the human acts.
                </p>
              </div>
              {/* Card 2 — Python Candidate Screening */}
              <div
                className="rounded-xl p-5 space-y-2"
                style={{
                  backgroundColor: "var(--color-nt-surface)",
                  border: "1px solid var(--color-nt-border)",
                }}
              >
                <div className="flex items-center gap-2">
                  <FlaskConical
                    className="h-4 w-4 flex-shrink-0"
                    style={{ color: "var(--color-nt-blue)" }}
                  />
                  <span className="text-sm font-semibold" style={{ color: "var(--color-nt-text)" }}>
                    Python Candidate Screening
                  </span>
                </div>
                <p className="text-sm leading-relaxed" style={{ color: "var(--color-nt-secondary)" }}>
                  Quantitative filters systematically screen the watchlist: volume, structure, ATR-normalized range, relative strength.
                </p>
              </div>
              {/* Card 3 — LLM Pattern Recognition */}
              <div
                className="rounded-xl p-5 space-y-2"
                style={{
                  backgroundColor: "var(--color-nt-surface)",
                  border: "1px solid var(--color-nt-border)",
                }}
              >
                <div className="flex items-center gap-2">
                  <BrainCircuit
                    className="h-4 w-4 flex-shrink-0"
                    style={{ color: "var(--color-nt-blue)" }}
                  />
                  <span className="text-sm font-semibold" style={{ color: "var(--color-nt-text)" }}>
                    LLM Pattern Recognition
                  </span>
                </div>
                <p className="text-sm leading-relaxed" style={{ color: "var(--color-nt-secondary)" }}>
                  Language models detect patterns across sector data, news flow, and positioning to surface directional hypotheses at scale.
                </p>
              </div>
              {/* Card 4 — Reinforcement Learning Validation */}
              <div
                className="rounded-xl p-5 space-y-2"
                style={{
                  backgroundColor: "var(--color-nt-surface)",
                  border: "1px solid var(--color-nt-border)",
                }}
              >
                <div className="flex items-center gap-2">
                  <Activity
                    className="h-4 w-4 flex-shrink-0"
                    style={{ color: "var(--color-nt-blue)" }}
                  />
                  <span className="text-sm font-semibold" style={{ color: "var(--color-nt-text)" }}>
                    Reinforcement Learning Validation
                  </span>
                </div>
                <p className="text-sm leading-relaxed" style={{ color: "var(--color-nt-secondary)" }}>
                  An RL model trained on historical outcomes continuously refines signal quality, penalising false positives and recency bias.
                </p>
              </div>
            </div>
            <p
              className="text-xs italic"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              Currently live paper trading — all results shown are simulated with no real capital at risk.
            </p>
          </section>

          {/* ── Sign in CTA ── */}
          <div className="flex justify-center">
            <button
              onClick={() => router.push("/waitlist")}
              className="animate-fade-in inline-flex items-center gap-1.5 text-sm font-medium transition-opacity hover:opacity-60"
              style={{ color: "var(--color-nt-blue)", background: "none", border: "none", padding: 0, cursor: "pointer" }}
            >
              Sign in to view full dashboard
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>

          {/* ── Footer ── */}
          <div className="flex flex-col items-center gap-2 text-center">
            <p
              className="text-xs"
              style={{ color: "var(--color-nt-muted)" }}
            >
              Foundry is a research platform. No financial advice is provided.
              Past simulated performance does not guarantee future results.
            </p>
            <div
              className="flex items-center gap-4 text-xs"
              style={{ color: "var(--color-nt-secondary)" }}
            >
              <Link href="/whitepaper" style={{ color: "var(--color-nt-blue)", textDecoration: "none" }}>
                Read the whitepaper
              </Link>
              <span style={{ color: "var(--color-nt-muted)" }}>·</span>
              <Link href="/terms" style={{ color: "var(--color-nt-secondary)", textDecoration: "none" }}>
                Terms &amp; Conditions
              </Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
