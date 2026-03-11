"use client";

import { Fragment, useEffect, useState, useCallback, useMemo } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";
import {
  DollarSign,
  TrendingUp,
  Wallet,
  Zap,
  BarChart2,
  RefreshCw,
  Play,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  ArrowUp,
  ArrowDown,
  CheckCircle2,
  X,
  Check,
  Trophy,
  TrendingDown,
  Activity,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import { api, type Account, type Theme, type WatchlistItem, type Position, type AlertItem, type PipelineResult } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { ScrollArea } from "@/components/ui/scroll-area";

import StatusBar from "@/components/ui/StatusBar";
import StatCard from "@/components/ui/StatCard";
import AlertCard from "@/components/ui/AlertCard";
import PipelineResultComponent from "@/components/ui/PipelineResult";
import ThemeScoreChart from "@/components/charts/ThemeScoreChart";
import VolumeRatioChart from "@/components/charts/VolumeRatioChart";
import PnlChart from "@/components/charts/PnlChart";
import PortfolioSparkline from "@/components/charts/PortfolioSparkline";
import ThemeDistribution from "@/components/charts/ThemeDistribution";

// ── Formatters ──────────────────────────────────────────────────────────────
function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return "—";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}
function fmtUsd(n: number | null | undefined): string {
  if (n == null) return "—";
  return "$" + fmt(n);
}
function fmtVol(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(0) + "K";
  return n.toFixed(0);
}
function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  const pct = n * 100;
  return (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%";
}

// ── Status dot colours ───────────────────────────────────────────────────────
const STATUS_DOT: Record<string, string> = {
  hot: "#FF3B30",
  emerging: "#FF9500",
  cooling: "#4d9fff",
  dead: "#6E6E73",
};

// ── Reusable card wrapper ────────────────────────────────────────────────────
function Panel({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl ${className}`}
      style={{ backgroundColor: "#FFFFFF", border: "1px solid #D2D2D7" }}
    >
      {children}
    </div>
  );
}

// ── Empty state ──────────────────────────────────────────────────────────────
function EmptyState({ message }: { message: string }) {
  return (
    <div className="py-16 text-center">
      <Activity size={28} style={{ color: "#D2D2D7", margin: "0 auto 10px" }} />
      <p style={{ color: "#6E6E73", fontSize: "13px" }}>{message}</p>
    </div>
  );
}

// ── Table header cell ────────────────────────────────────────────────────────
function TH({ children }: { children?: React.ReactNode }) {
  return (
    <th
      className="text-left px-4 py-3 text-[10px] font-semibold uppercase tracking-wider"
      style={{ color: "#6E6E73", borderBottom: "1px solid #1e1e2e" }}
    >
      {children}
    </th>
  );
}

// ── Main dashboard ───────────────────────────────────────────────────────────
export default function Dashboard() {
  const [account, setAccount] = useState<Account | null>(null);
  const [themes, setThemes] = useState<Theme[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [activeTab, setActiveTab] = useState("themes");
  const [alertFilter, setAlertFilter] = useState("all");
  const [expandedPositions, setExpandedPositions] = useState<Set<number>>(new Set());
  const [sessionReady, setSessionReady] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const [acc, th, wl, pos, al] = await Promise.allSettled([
        api.getAccount(),
        api.getThemes(),
        api.getWatchlist(),
        api.getPositions(),
        api.getAlerts(),
      ]);
      if (acc.status === "fulfilled") setAccount(acc.value);
      if (th.status === "fulfilled") setThemes(th.value);
      if (wl.status === "fulfilled") setWatchlist(wl.value);
      if (pos.status === "fulfilled") setPositions(pos.value);
      if (al.status === "fulfilled") setAlerts(al.value);
      setError(null);
      setLastRefreshed(new Date());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to refresh data");
    } finally {
      setRefreshing(false);
    }
  }, []);

  // Attach Supabase access token — gates the data fetch until session is confirmed
  useEffect(() => {
    // In local dev, skip auth and load immediately
    if (process.env.NODE_ENV === "development") {
      api.setAuthToken(null);
      setSessionReady(true);
      return;
    }
    supabase.auth.getSession().then(({ data: { session } }) => {
      api.setAuthToken(session?.access_token ?? null);
      setSessionReady(true);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      api.setAuthToken(session?.access_token ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!sessionReady) return;
    refresh();
    const interval = setInterval(refresh, 30_000);
    return () => clearInterval(interval);
  }, [refresh, sessionReady]);

  const runPipeline = async () => {
    setPipelineLoading(true);
    setPipelineResult(null);
    try {
      const result = await api.runFullPipeline();
      setPipelineResult(result);
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Pipeline failed");
    } finally {
      setPipelineLoading(false);
    }
  };

  const unreadAlerts = alerts.filter((a) => !a.acknowledged);

  const filteredAlerts = useMemo(() => {
    switch (alertFilter) {
      case "unread":   return alerts.filter((a) => !a.acknowledged);
      case "critical": return alerts.filter((a) => a.severity === "critical" || a.severity === "action");
      case "warning":  return alerts.filter((a) => a.severity === "warning");
      case "info":     return alerts.filter((a) => a.severity === "info");
      default:         return alerts;
    }
  }, [alerts, alertFilter]);

  const winRate = useMemo(() => {
    if (!positions.length) return 0;
    return Math.round((positions.filter((p) => p.unrealized_pnl > 0).length / positions.length) * 100);
  }, [positions]);

  const totalPnl = positions.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);

  const biggestWinner = positions.length
    ? positions.reduce((best, p) => (p.unrealized_pnl > best.unrealized_pnl ? p : best), positions[0])
    : null;
  const biggestLoser = positions.length
    ? positions.reduce((worst, p) => (p.unrealized_pnl < worst.unrealized_pnl ? p : worst), positions[0])
    : null;

  const togglePosition = (id: number) => {
    setExpandedPositions((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleAck = async (id: number) => {
    await api.ackAlert(id);
    refresh();
  };
  const handleAckAll = async () => {
    await api.ackAllAlerts();
    refresh();
  };

  // ── Tab definitions ────────────────────────────────────────────────────────
  const tabs = [
    { value: "themes",    label: "🔥 Themes",    count: themes.length },
    { value: "watchlist", label: "📋 Watchlist",  count: watchlist.length },
    { value: "positions", label: "💼 Positions",  count: positions.length },
    { value: "alerts",    label: "🔔 Alerts",     count: unreadAlerts.length || null },
  ];

  // ── Row hover helpers (memoized style mutators) ────────────────────────────
  const rowEnter = (e: React.MouseEvent<HTMLTableRowElement>) => {
    (e.currentTarget as HTMLTableRowElement).style.backgroundColor = "#F5F5F7";
  };
  const rowLeave = (e: React.MouseEvent<HTMLTableRowElement>) => {
    (e.currentTarget as HTMLTableRowElement).style.backgroundColor = "transparent";
  };

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#F5F5F7" }}>
      <StatusBar />

      <main className="pt-10">
        <div style={{ maxWidth: "1600px", margin: "0 auto", padding: "24px" }} className="space-y-5">

          {/* ── Header ──────────────────────────────────────────────────── */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold" style={{ color: "#AEAEB2" }}>
              Foundry
            </span>

            <div className="flex items-center gap-3">
              {lastRefreshed && (
                <span className="text-[11px]" style={{ color: "#6E6E73" }}>
                  Updated {formatDistanceToNow(lastRefreshed, { addSuffix: true })}
                </span>
              )}
              <button
                onClick={refresh}
                disabled={refreshing}
                className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg transition-all disabled:opacity-40"
                style={{ border: "1px solid #2a2a3e", color: "#6E6E73", backgroundColor: "transparent" }}
                onMouseEnter={(e) => {
                  const el = e.currentTarget as HTMLButtonElement;
                  el.style.borderColor = "#4d9fff";
                  el.style.color = "#1D1D1F";
                }}
                onMouseLeave={(e) => {
                  const el = e.currentTarget as HTMLButtonElement;
                  el.style.borderColor = "#D2D2D7";
                  el.style.color = "#6E6E73";
                }}
              >
                <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
                Refresh
              </button>
              <button
                onClick={runPipeline}
                disabled={pipelineLoading}
                className="flex items-center gap-2 px-4 py-1.5 text-xs font-semibold rounded-lg transition-opacity hover:opacity-70 disabled:opacity-40"
                style={{ background: "none", border: "1px solid #0066CC", color: "#0066CC" }}
              >
                <Play size={12} className={pipelineLoading ? "animate-pulse" : ""} />
                {pipelineLoading ? "Running…" : "Run Pipeline"}
              </button>
            </div>
          </div>

          {/* ── Error banner ─────────────────────────────────────────────── */}
          {error && (
            <div
              className="flex items-center gap-3 rounded-xl px-4 py-3"
              style={{
                backgroundColor: "rgba(255,59,48,0.07)",
                border: "1px solid rgba(255,59,48,0.3)",
                boxShadow: "0 0 20px rgba(255,59,48,0.08)",
              }}
            >
              <AlertCircle size={16} style={{ color: "#FF3B30", flexShrink: 0 }} />
              <span className="text-sm flex-1" style={{ color: "#FF3B30" }}>{error}</span>
              <button
                onClick={() => setError(null)}
                className="text-xs px-2 py-1 rounded"
                style={{ color: "#FF3B30", backgroundColor: "rgba(255,59,48,0.1)" }}
              >
                Dismiss
              </button>
              <button
                onClick={refresh}
                className="text-xs px-2 py-1 rounded font-semibold"
                style={{ color: "#0a0a0f", backgroundColor: "#FF3B30" }}
              >
                Retry
              </button>
            </div>
          )}

          {/* ── Account Metrics ──────────────────────────────────────────── */}
          {account ? (
            <div className="grid grid-cols-5 gap-3">
              <StatCard icon={DollarSign} label="Portfolio Value" value={fmtUsd(account.portfolio_value)} borderColor="green" />
              <StatCard icon={TrendingUp} label="Equity"          value={fmtUsd(account.equity)}          borderColor="green" />
              <StatCard icon={Wallet}     label="Cash"             value={fmtUsd(account.cash)}             borderColor="blue"  />
              <StatCard icon={Zap}        label="Buying Power"     value={fmtUsd(account.buying_power)}     borderColor="blue"  />
              <StatCard
                icon={BarChart2}
                label="Daily P&L"
                value={fmtUsd(account.daily_pnl)}
                borderColor={account.daily_pnl >= 0 ? "green" : "red"}
                positive={account.daily_pnl >= 0}
                negative={account.daily_pnl < 0}
              />
            </div>
          ) : (
            <div className="grid grid-cols-5 gap-3">
              {[...Array(5)].map((_, i) => (
                <div
                  key={i}
                  className="h-20 rounded-xl skeleton"
                  style={{ border: "1px solid #1e1e2e" }}
                />
              ))}
            </div>
          )}

          {/* ── Mini Charts Row ──────────────────────────────────────────── */}
          <div className="grid grid-cols-3 gap-3">
            {/* Portfolio sparkline */}
            <Panel className="p-4">
              <div className="flex items-center justify-between mb-1">
                <span
                  className="text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#6E6E73" }}
                >
                  Portfolio Value
                </span>
                <span
                  className="text-[10px] px-2 py-0.5 rounded-full"
                  style={{ backgroundColor: "#D2D2D7", color: "#6E6E73" }}
                >
                  30d Simulated
                </span>
              </div>
              {account && (
                <div
                  className="text-sm font-bold tabular-nums mt-0.5"
                  style={{ color: "#34C759", fontVariantNumeric: "tabular-nums" }}
                >
                  {fmtUsd(account.equity)}
                </div>
              )}
              <PortfolioSparkline equity={account?.equity} />
            </Panel>

            {/* Theme distribution */}
            <Panel className="p-4">
              <span
                className="text-[10px] font-semibold uppercase tracking-wider"
                style={{ color: "#6E6E73" }}
              >
                Active Themes
              </span>
              <div className="flex items-center justify-around mt-2">
                {(["hot", "emerging", "cooling", "dead"] as const).map((s) => {
                  const count = themes.filter((t) => t.status === s).length;
                  return (
                    <div key={s} className="text-center">
                      <div
                        className="text-base font-bold tabular-nums"
                        style={{ color: STATUS_DOT[s], fontVariantNumeric: "tabular-nums" }}
                      >
                        {count}
                      </div>
                      <div className="text-[9px] uppercase tracking-wider" style={{ color: "#6E6E73" }}>
                        {s}
                      </div>
                    </div>
                  );
                })}
              </div>
              <ThemeDistribution themes={themes} />
            </Panel>

            {/* Win rate gauge */}
            <Panel className="p-4 relative">
              <span
                className="text-[10px] font-semibold uppercase tracking-wider"
                style={{ color: "#6E6E73" }}
              >
                Win Rate
              </span>
              <div style={{ height: 72, marginTop: 8 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={[
                        { value: winRate },
                        { value: Math.max(0, 100 - winRate) },
                      ]}
                      cx="50%"
                      cy="100%"
                      startAngle={180}
                      endAngle={0}
                      innerRadius={38}
                      outerRadius={50}
                      paddingAngle={0}
                      dataKey="value"
                      strokeWidth={0}
                    >
                      <Cell fill="#34C759" />
                      <Cell fill="#D2D2D7" />
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div
                className="absolute flex flex-col items-center"
                style={{ bottom: "18px", left: 0, right: 0 }}
              >
                <span
                  className="text-2xl font-bold tabular-nums"
                  style={{
                    color: winRate > 50 ? "#34C759" : winRate > 0 ? "#FF9500" : "#6E6E73",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {winRate}%
                </span>
                <span className="text-[10px]" style={{ color: "#6E6E73" }}>
                  {positions.length} position{positions.length !== 1 ? "s" : ""}
                </span>
              </div>
            </Panel>
          </div>

          {/* ── Pipeline Result ──────────────────────────────────────────── */}
          {pipelineResult && <PipelineResultComponent result={pipelineResult} />}

          {/* ── Tabs ─────────────────────────────────────────────────────── */}
          <div>
            {/* Tab bar */}
            <div
              className="flex gap-1 p-1 rounded-xl w-fit mb-4"
              style={{ backgroundColor: "#FFFFFF", border: "1px solid #D2D2D7" }}
            >
              {tabs.map((tab) => (
                <button
                  key={tab.value}
                  onClick={() => setActiveTab(tab.value)}
                  className="flex items-center gap-2 px-4 py-2 text-xs font-medium rounded-lg transition-all duration-200"
                  style={{
                    backgroundColor:
                      activeTab === tab.value ? "rgba(0,102,204,0.12)" : "transparent",
                    color: activeTab === tab.value ? "#0066CC" : "#6E6E73",
                    border:
                      activeTab === tab.value
                        ? "1px solid rgba(0,102,204,0.25)"
                        : "1px solid transparent",
                    boxShadow:
                      activeTab === tab.value ? "0 0 8px rgba(0,102,204,0.08)" : "none",
                  }}
                >
                  {tab.label}
                  {tab.count != null && tab.count > 0 && (
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded-full tabular-nums"
                      style={{
                        backgroundColor:
                          activeTab === tab.value
                            ? "rgba(0,102,204,0.2)"
                            : "rgba(136,136,170,0.15)",
                        color: activeTab === tab.value ? "#0066CC" : "#6E6E73",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {tab.count}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* ── THEMES TAB ─────────────────────────────────────────────── */}
            {activeTab === "themes" && (
              <div className="space-y-4 animate-fade-in">
                <Panel className="p-5">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold" style={{ color: "#1D1D1F" }}>
                      Theme Signal Breakdown
                    </h3>
                    <div className="flex items-center gap-4">
                      {[["News", "#4d9fff"], ["Social", "#a78bfa"], ["ETF", "#FF9500"]].map(
                          ([k, c]) => (
                            <span
                              key={k}
                              className="flex items-center gap-1.5 text-[10px]"
                              style={{ color: "#6E6E73" }}
                            >
                              <span
                                className="w-2 h-2 rounded-sm inline-block"
                                style={{ backgroundColor: c }}
                              />
                              {k}
                            </span>
                          )
                        )}
                    </div>
                  </div>
                  <ThemeScoreChart themes={themes} />
                </Panel>

                <Panel className="overflow-hidden">
                  {themes.length === 0 ? (
                    <EmptyState message="No themes detected. Run the pipeline to scan." />
                  ) : (
                    <table className="w-full">
                      <thead>
                        <tr>
                          <TH>Theme</TH>
                          <TH>Status</TH>
                          <TH>Score</TH>
                          <TH>Signals</TH>
                          <TH>Keywords</TH>
                          <TH>Updated</TH>
                        </tr>
                      </thead>
                      <tbody>
                        {themes.map((t) => (
                          <tr
                            key={t.id}
                            className="transition-colors"
                            style={{ borderBottom: "1px solid #1e1e2e" }}
                            onMouseEnter={rowEnter}
                            onMouseLeave={rowLeave}
                          >
                            <td className="px-4 py-3">
                              <span
                                className="font-semibold text-sm"
                                style={{ color: "#1D1D1F" }}
                              >
                                {t.name}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2">
                                <span className="relative flex h-2 w-2 flex-shrink-0">
                                  {t.status === "hot" && (
                                    <span
                                      className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                                      style={{ backgroundColor: STATUS_DOT[t.status] }}
                                    />
                                  )}
                                  <span
                                    className="relative inline-flex rounded-full h-2 w-2"
                                    style={{
                                      backgroundColor: STATUS_DOT[t.status] ?? "#6E6E73",
                                    }}
                                  />
                                </span>
                                <span
                                  className="text-xs capitalize"
                                  style={{ color: STATUS_DOT[t.status] ?? "#6E6E73" }}
                                >
                                  {t.status}
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2">
                                <div
                                  className="w-16 h-1.5 rounded-full overflow-hidden"
                                  style={{ backgroundColor: "#D2D2D7" }}
                                >
                                  <div
                                    className="h-full rounded-full"
                                    style={{
                                      width: `${Math.min(100, ((t.score ?? 0) / 3) * 100)}%`,
                                      backgroundColor: STATUS_DOT[t.status] ?? "#34C759",
                                    }}
                                  />
                                </div>
                                <span
                                  className="text-xs tabular-nums"
                                  style={{
                                    color: "#6E6E73",
                                    fontVariantNumeric: "tabular-nums",
                                  }}
                                >
                                  {fmt(t.score)}
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <div
                                className="flex gap-3 text-[11px]"
                                style={{ fontVariantNumeric: "tabular-nums" }}
                              >
                                <span style={{ color: "#4d9fff" }}>N:{fmt(t.news_score, 1)}</span>
                                <span style={{ color: "#a78bfa" }}>S:{fmt(t.social_score, 1)}</span>
                                <span style={{ color: "#FF9500" }}>E:{fmt(t.etf_score, 1)}</span>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex flex-wrap gap-1">
                                {(t.keywords || "")
                                  .split(",")
                                  .slice(0, 4)
                                  .filter((k) => k.trim())
                                  .map((kw, i) => (
                                    <span
                                      key={i}
                                      className="text-[10px] px-2 py-0.5 rounded-full"
                                      style={{ backgroundColor: "#D2D2D7", color: "#6E6E73" }}
                                    >
                                      {kw.trim()}
                                    </span>
                                  ))}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-[11px]" style={{ color: "#6E6E73" }}>
                                {t.updated_at
                                  ? formatDistanceToNow(new Date(t.updated_at), { addSuffix: true })
                                  : "—"}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Panel>
              </div>
            )}

            {/* ── WATCHLIST TAB ──────────────────────────────────────────── */}
            {activeTab === "watchlist" && (
              <div className="space-y-4 animate-fade-in">
                <Panel className="p-5">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold" style={{ color: "#1D1D1F" }}>
                      Volume Ratio by Symbol
                    </h3>
                    <div className="flex items-center gap-4">
                      {[
                        ["Near Breakout", "#34C759"],
                        ["Watching", "#FF9500"],
                      ].map(([k, c]) => (
                        <span
                          key={k}
                          className="flex items-center gap-1.5 text-[10px]"
                          style={{ color: "#6E6E73" }}
                        >
                          <span
                            className="w-2 h-2 rounded-sm inline-block"
                            style={{ backgroundColor: c }}
                          />
                          {k}
                        </span>
                      ))}
                    </div>
                  </div>
                  <VolumeRatioChart watchlist={watchlist} />
                </Panel>

                <Panel className="overflow-hidden">
                  {watchlist.length === 0 ? (
                    <EmptyState message="No watchlist items. Run the pipeline to build." />
                  ) : (
                    <table className="w-full">
                      <thead>
                        <tr>
                          <TH>Symbol</TH>
                          <TH>Theme</TH>
                          <TH>Price</TH>
                          <TH>Float / Avg Vol</TH>
                          <TH>Structure</TH>
                          <TH>Breakout</TH>
                          <TH>Vol Ratio</TH>
                          <TH>Rank</TH>
                        </tr>
                      </thead>
                      <tbody>
                        {watchlist.map((w) => (
                          <tr
                            key={w.id}
                            className="transition-colors"
                            style={{ borderBottom: "1px solid #1e1e2e" }}
                            onMouseEnter={rowEnter}
                            onMouseLeave={rowLeave}
                          >
                            <td className="px-4 py-3">
                              <div className="font-bold text-sm" style={{ color: "#1D1D1F" }}>
                                {w.symbol}
                              </div>
                              {w.company_name && (
                                <div
                                  className="text-[11px] truncate"
                                  style={{ color: "#6E6E73", maxWidth: "120px" }}
                                >
                                  {w.company_name}
                                </div>
                              )}
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-[11px]" style={{ color: "#6E6E73" }}>
                                {w.theme_name ?? "—"}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className="text-sm font-semibold tabular-nums"
                                style={{
                                  color: "#1D1D1F",
                                  fontVariantNumeric: "tabular-nums",
                                }}
                              >
                                {fmtUsd(w.price)}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div
                                className="text-[11px]"
                                style={{ color: "#6E6E73", fontVariantNumeric: "tabular-nums" }}
                              >
                                <span>{fmtVol(w.float_shares)}</span>
                                <span style={{ color: "#6E6E73" }}> / </span>
                                <span>{fmtVol(w.avg_volume)}</span>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              {w.structure_clean ? (
                                <CheckCircle2 size={16} style={{ color: "#34C759" }} />
                              ) : (
                                <X size={16} style={{ color: "#FF3B30" }} />
                              )}
                            </td>
                            <td className="px-4 py-3">
                              {w.near_breakout ? (
                                <div className="flex items-center gap-1.5">
                                  <span className="relative flex h-2 w-2">
                                    <span
                                      className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                                      style={{ backgroundColor: "#34C759" }}
                                    />
                                    <span
                                      className="relative inline-flex rounded-full h-2 w-2"
                                      style={{ backgroundColor: "#34C759" }}
                                    />
                                  </span>
                                  <span
                                    className="text-[11px] font-semibold uppercase tracking-wide"
                                    style={{ color: "#34C759" }}
                                  >
                                    BREAKOUT
                                  </span>
                                </div>
                              ) : (
                                <span style={{ color: "#6E6E73" }}>—</span>
                              )}
                            </td>
                            <td className="px-4 py-3">
                              {w.volume_ratio != null ? (
                                <span
                                  className="text-sm font-semibold tabular-nums"
                                  style={{
                                    color:
                                      w.volume_ratio > 2
                                        ? "#34C759"
                                        : w.volume_ratio > 1
                                        ? "#FF9500"
                                        : "#6E6E73",
                                    fontVariantNumeric: "tabular-nums",
                                  }}
                                >
                                  {w.volume_ratio.toFixed(1)}x
                                </span>
                              ) : (
                                <span style={{ color: "#6E6E73" }}>—</span>
                              )}
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2">
                                <div
                                  className="w-12 h-1 rounded-full overflow-hidden"
                                  style={{ backgroundColor: "#D2D2D7" }}
                                >
                                  <div
                                    className="h-full rounded-full"
                                    style={{
                                      width: `${Math.min(100, (w.rank_score ?? 0) * 100)}%`,
                                      backgroundColor: "#4d9fff",
                                    }}
                                  />
                                </div>
                                <span
                                  className="text-[11px] tabular-nums"
                                  style={{
                                    color: "#6E6E73",
                                    fontVariantNumeric: "tabular-nums",
                                  }}
                                >
                                  {fmt(w.rank_score)}
                                </span>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Panel>
              </div>
            )}

            {/* ── POSITIONS TAB ─────────────────────────────────────────── */}
            {activeTab === "positions" && (
              <div className="animate-fade-in">
                {positions.length === 0 ? (
                  <Panel>
                    <EmptyState message="No open positions. The pipeline will enter trades on breakout signals." />
                  </Panel>
                ) : (
                  <div className="space-y-4">
                    {/* Summary row */}
                    <div className="grid grid-cols-4 gap-3">
                      <div
                        className="col-span-2 rounded-xl p-4"
                        style={{
                          backgroundColor: "#111118",
                          borderTop: "1px solid #1e1e2e",
                          borderRight: "1px solid #1e1e2e",
                          borderBottom: "1px solid #1e1e2e",
                          borderLeft: `3px solid ${totalPnl >= 0 ? "#34C759" : "#FF3B30"}`,
                        }}
                      >
                        <div
                          className="text-[10px] font-semibold uppercase tracking-wider mb-1"
                          style={{ color: "#6E6E73" }}
                        >
                          Total Unrealized P&L
                        </div>
                        <div
                          className="text-3xl font-bold tabular-nums"
                          style={{
                            color: totalPnl >= 0 ? "#34C759" : "#FF3B30",
                            fontVariantNumeric: "tabular-nums",
                            textShadow:
                              totalPnl >= 0
                                ? "0 0 20px rgba(52,199,89,0.3)"
                                : "0 0 20px rgba(255,59,48,0.3)",
                          }}
                        >
                          {fmtUsd(totalPnl)}
                        </div>
                      </div>

                      {biggestWinner && (
                        <div
                          className="rounded-xl p-4"
                          style={{
                            backgroundColor: "#111118",
                            borderTop: "1px solid #1e1e2e",
                            borderRight: "1px solid #1e1e2e",
                            borderBottom: "1px solid #1e1e2e",
                            borderLeft: "3px solid #00d4aa",
                          }}
                        >
                          <div
                            className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider mb-1"
                            style={{ color: "#6E6E73" }}
                          >
                            <Trophy size={10} style={{ color: "#FF9500" }} />
                            Best Winner
                          </div>
                          <div className="font-bold text-sm" style={{ color: "#1D1D1F" }}>
                            {biggestWinner.symbol}
                          </div>
                          <div
                            className="text-sm tabular-nums font-semibold"
                            style={{ color: "#34C759", fontVariantNumeric: "tabular-nums" }}
                          >
                            {fmtUsd(biggestWinner.unrealized_pnl)}
                          </div>
                        </div>
                      )}

                      {biggestLoser && (
                        <div
                          className="rounded-xl p-4"
                          style={{
                            backgroundColor: "#111118",
                            borderTop: "1px solid #1e1e2e",
                            borderRight: "1px solid #1e1e2e",
                            borderBottom: "1px solid #1e1e2e",
                            borderLeft: "3px solid #ff4d6d",
                          }}
                        >
                          <div
                            className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider mb-1"
                            style={{ color: "#6E6E73" }}
                          >
                            <TrendingDown size={10} style={{ color: "#FF3B30" }} />
                            Biggest Loser
                          </div>
                          <div className="font-bold text-sm" style={{ color: "#1D1D1F" }}>
                            {biggestLoser.symbol}
                          </div>
                          <div
                            className="text-sm tabular-nums font-semibold"
                            style={{ color: "#FF3B30", fontVariantNumeric: "tabular-nums" }}
                          >
                            {fmtUsd(biggestLoser.unrealized_pnl)}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* P&L Chart */}
                    <Panel className="p-5">
                      <h3 className="text-sm font-semibold mb-3" style={{ color: "#1D1D1F" }}>
                        Position P&L
                      </h3>
                      <PnlChart positions={positions} />
                    </Panel>

                    {/* Positions table */}
                    <Panel className="overflow-hidden">
                      <table className="w-full">
                        <thead>
                          <tr>
                            <TH>Symbol</TH>
                            <TH>Qty</TH>
                            <TH>Entry → Current</TH>
                            <TH>P&L</TH>
                            <TH>Market Value</TH>
                            <TH>Stop Loss</TH>
                            <TH></TH>
                          </tr>
                        </thead>
                        <tbody>
                          {positions.map((p) => {
                            const isPos = p.unrealized_pnl >= 0;
                            const isExpanded = expandedPositions.has(p.id);
                            return (
                              <Fragment key={p.id}>
                                <tr
                                  className="transition-colors cursor-pointer"
                                  style={{
                                    borderBottom: isExpanded
                                      ? "none"
                                      : "1px solid #1e1e2e",
                                  }}
                                  onClick={() => togglePosition(p.id)}
                                  onMouseEnter={rowEnter}
                                  onMouseLeave={rowLeave}
                                >
                                  <td className="px-4 py-3">
                                    <div className="flex items-center gap-2">
                                      <span
                                        className="font-bold text-sm"
                                        style={{ color: "#1D1D1F" }}
                                      >
                                        {p.symbol}
                                      </span>
                                      <span
                                        className="text-[10px] px-1.5 py-0.5 rounded font-semibold"
                                        style={{
                                          backgroundColor: "rgba(77,159,255,0.1)",
                                          color: "#4d9fff",
                                        }}
                                      >
                                        L{p.pyramid_level}
                                      </span>
                                    </div>
                                  </td>
                                  <td className="px-4 py-3">
                                    <span
                                      className="text-sm tabular-nums"
                                      style={{
                                        color: "#6E6E73",
                                        fontVariantNumeric: "tabular-nums",
                                      }}
                                    >
                                      {p.qty}
                                    </span>
                                  </td>
                                  <td className="px-4 py-3">
                                    <div
                                      className="flex items-center gap-1.5 text-sm tabular-nums"
                                      style={{ fontVariantNumeric: "tabular-nums" }}
                                    >
                                      <span style={{ color: "#6E6E73" }}>
                                        {fmtUsd(p.avg_entry_price)}
                                      </span>
                                      {isPos ? (
                                        <ArrowUp size={12} style={{ color: "#34C759" }} />
                                      ) : (
                                        <ArrowDown size={12} style={{ color: "#FF3B30" }} />
                                      )}
                                      <span style={{ color: isPos ? "#34C759" : "#FF3B30" }}>
                                        {fmtUsd(p.current_price)}
                                      </span>
                                    </div>
                                  </td>
                                  <td className="px-4 py-3">
                                    <div
                                      className="font-bold tabular-nums"
                                      style={{
                                        color: isPos ? "#34C759" : "#FF3B30",
                                        fontVariantNumeric: "tabular-nums",
                                        textShadow: isPos
                                          ? "0 0 8px rgba(52,199,89,0.3)"
                                          : "0 0 8px rgba(255,59,48,0.25)",
                                      }}
                                    >
                                      {fmtUsd(p.unrealized_pnl)}
                                    </div>
                                    <div
                                      className="text-[11px] tabular-nums"
                                      style={{
                                        color: isPos
                                          ? "rgba(52,199,89,0.65)"
                                          : "rgba(255,59,48,0.65)",
                                        fontVariantNumeric: "tabular-nums",
                                      }}
                                    >
                                      {fmtPct(p.unrealized_pnl_pct)}
                                    </div>
                                  </td>
                                  <td className="px-4 py-3">
                                    <span
                                      className="text-sm tabular-nums"
                                      style={{
                                        color: "#6E6E73",
                                        fontVariantNumeric: "tabular-nums",
                                      }}
                                    >
                                      {fmtUsd(p.market_value)}
                                    </span>
                                  </td>
                                  <td className="px-4 py-3">
                                    {p.stop_loss_price ? (
                                      <div className="flex items-center gap-1.5">
                                        <div
                                          className="w-0.5 h-4 rounded-full"
                                          style={{ backgroundColor: "#FF3B30" }}
                                        />
                                        <span
                                          className="text-sm tabular-nums"
                                          style={{
                                            color: "#FF3B30",
                                            fontVariantNumeric: "tabular-nums",
                                          }}
                                        >
                                          {fmtUsd(p.stop_loss_price)}
                                        </span>
                                      </div>
                                    ) : (
                                      <span style={{ color: "#6E6E73" }}>—</span>
                                    )}
                                  </td>
                                  <td className="px-4 py-3">
                                    {(p.actions?.length ?? 0) > 0 &&
                                      (isExpanded ? (
                                        <ChevronDown size={14} style={{ color: "#6E6E73" }} />
                                      ) : (
                                        <ChevronRight size={14} style={{ color: "#6E6E73" }} />
                                      ))}
                                  </td>
                                </tr>

                                {/* Expandable trade history */}
                                {isExpanded && (p.actions?.length ?? 0) > 0 && (
                                  <tr style={{ borderBottom: "1px solid #1e1e2e" }}>
                                    <td
                                      colSpan={7}
                                      className="px-4 pb-3 pt-0"
                                      style={{ backgroundColor: "#F5F5F7" }}
                                    >
                                      <div
                                        className="rounded-lg p-3 mt-1"
                                        style={{ border: "1px solid #1e1e2e" }}
                                      >
                                        <div
                                          className="text-[10px] font-semibold uppercase tracking-wider mb-2"
                                          style={{ color: "#6E6E73" }}
                                        >
                                          Trade History
                                        </div>
                                        <div className="space-y-1.5">
                                          {p.actions.map((a, ai) => (
                                            <div
                                              key={ai}
                                              className="flex items-center gap-3 text-[11px]"
                                            >
                                              <span
                                                className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase"
                                                style={{
                                                  backgroundColor:
                                                    a.type === "buy"
                                                      ? "rgba(52,199,89,0.1)"
                                                      : "rgba(255,59,48,0.1)",
                                                  color:
                                                    a.type === "buy" ? "#34C759" : "#FF3B30",
                                                }}
                                              >
                                                {a.type}
                                              </span>
                                              <span
                                                className="tabular-nums"
                                                style={{
                                                  color: "#6E6E73",
                                                  fontVariantNumeric: "tabular-nums",
                                                }}
                                              >
                                                {a.qty} @ {fmtUsd(a.price)}
                                              </span>
                                              <span style={{ color: "#6E6E73" }}>{a.reason}</span>
                                              <span
                                                className="ml-auto"
                                                style={{ color: "#6E6E73" }}
                                              >
                                                {a.at
                                                  ? formatDistanceToNow(new Date(a.at), {
                                                      addSuffix: true,
                                                    })
                                                  : ""}
                                              </span>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    </td>
                                  </tr>
                                )}
                              </Fragment>
                            );
                          })}
                        </tbody>
                      </table>
                    </Panel>
                  </div>
                )}
              </div>
            )}

            {/* ── ALERTS TAB ───────────────────────────────────────────── */}
            {activeTab === "alerts" && (
              <div className="space-y-3 animate-fade-in">
                {/* Filter pills + actions */}
                <div className="flex items-center justify-between">
                  <div className="flex gap-1.5">
                    {[
                      { key: "all",      label: "All",      count: alerts.length },
                      { key: "critical", label: "Critical", count: null },
                      { key: "warning",  label: "Warning",  count: null },
                      { key: "info",     label: "Info",     count: null },
                      { key: "unread",   label: "Unread",   count: unreadAlerts.length },
                    ].map((f) => (
                      <button
                        key={f.key}
                        onClick={() => setAlertFilter(f.key)}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-lg transition-all"
                        style={{
                          backgroundColor:
                            alertFilter === f.key ? "rgba(52,199,89,0.12)" : "#111118",
                          border: `1px solid ${
                            alertFilter === f.key ? "rgba(52,199,89,0.3)" : "#D2D2D7"
                          }`,
                          color: alertFilter === f.key ? "#34C759" : "#6E6E73",
                        }}
                      >
                        {f.label}
                        {f.count != null && f.count > 0 && (
                          <span
                            className="text-[10px] px-1.5 rounded-full"
                            style={{
                              backgroundColor:
                                alertFilter === f.key
                                  ? "rgba(52,199,89,0.2)"
                                  : "#D2D2D7",
                              color:
                                alertFilter === f.key ? "#34C759" : "#6E6E73",
                            }}
                          >
                            {f.count}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>

                  {unreadAlerts.length > 0 && (
                    <button
                      onClick={handleAckAll}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-lg transition-all"
                      style={{ border: "1px solid #2a2a3e", color: "#6E6E73", backgroundColor: "transparent" }}
                      onMouseEnter={(e) => {
                        const el = e.currentTarget as HTMLButtonElement;
                        el.style.color = "#1D1D1F";
                        el.style.borderColor = "#4d9fff";
                      }}
                      onMouseLeave={(e) => {
                        const el = e.currentTarget as HTMLButtonElement;
                        el.style.color = "#6E6E73";
                        el.style.borderColor = "#D2D2D7";
                      }}
                    >
                      <Check size={11} />
                      Mark All Read
                    </button>
                  )}
                </div>

                {/* Alert cards */}
                <ScrollArea className="h-[500px]">
                  {filteredAlerts.length === 0 ? (
                    <div className="py-16 text-center">
                      <Activity size={28} style={{ color: "#D2D2D7", margin: "0 auto 10px" }} />
                      <p style={{ color: "#6E6E73", fontSize: "13px" }}>
                        No alerts in this category.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-2 pr-2">
                      {filteredAlerts.map((a) => (
                        <AlertCard key={a.id} alert={a} onAck={handleAck} />
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
