"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, Activity, Clock, BarChart2, Layers, ArrowRight } from "lucide-react";

interface PublicStats {
  total_closed_trades: number;
  win_rate_pct: number;
  avg_hold_days: number;
  total_realized_pnl_pct: number;
  open_positions: number;
  system_status: string;
}

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

export default function HomePage() {
  const router = useRouter();
  const [stats, setStats] = useState<PublicStats | null>(null);
  const [loading, setLoading] = useState(true);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  useEffect(() => {
    fetch(`${apiUrl}/api/public/stats`)
      .then((r) => r.json())
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, [apiUrl]);

  const statusColor =
    stats?.system_status === "running"
      ? "var(--color-nt-green)"
      : stats?.system_status === "paused"
      ? "var(--color-nt-amber)"
      : "var(--color-nt-muted)";

  return (
    <div className="min-h-screen" style={{ backgroundColor: "var(--color-nt-bg)", color: "var(--color-nt-text)" }}>

      {/* Nav */}
      <nav
        className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4"
        style={{
          background: "rgba(10,10,15,0.85)",
          backdropFilter: "blur(12px)",
          borderBottom: "1px solid var(--color-nt-border)",
        }}
      >
        <span className="text-lg font-bold" style={{ color: "var(--color-nt-purple)" }}>
          Foundry
        </span>
        <button
          onClick={() => router.push("/login")}
          className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-opacity hover:opacity-80"
          style={{ background: "var(--color-nt-purple)", color: "#fff" }}
        >
          Sign in
        </button>
      </nav>

      {/* Hero */}
      <main className="flex min-h-screen flex-col items-center justify-center px-4 pt-20 pb-12">
        <div className="w-full max-w-2xl space-y-8">

          {/* Title block */}
          <div className="text-center space-y-3">
            <h1
              className="text-5xl font-bold tracking-tight"
              style={{ color: "var(--color-nt-purple)" }}
            >
              Foundry
            </h1>
            <p className="text-lg" style={{ color: "var(--color-nt-secondary)" }}>
              Sector-breakout trading — systematically identified, automatically executed.
            </p>
          </div>

          {/* Stats card */}
          <Card
            style={{
              backgroundColor: "var(--color-nt-surface)",
              borderColor: "var(--color-nt-border)",
            }}
          >
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium" style={{ color: "var(--color-nt-secondary)" }}>
                  Live Performance
                </CardTitle>
                {stats && (
                  <span
                    className="inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-semibold uppercase tracking-widest"
                    style={{
                      color: statusColor,
                      background: `color-mix(in srgb, ${statusColor} 15%, transparent)`,
                      border: `1px solid color-mix(in srgb, ${statusColor} 30%, transparent)`,
                    }}
                  >
                    <span
                      className="animate-pulse-glow inline-block h-1.5 w-1.5 rounded-full"
                      style={{ background: statusColor }}
                    />
                    {stats.system_status}
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {loading ? (
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
                        <Icon className="h-3.5 w-3.5" style={{ color: "var(--color-nt-muted)" }} />
                        <span className="text-xs font-medium" style={{ color: "var(--color-nt-secondary)" }}>
                          {label}
                        </span>
                      </div>
                      <span
                        className="tabular-nums text-2xl font-bold"
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
            </CardContent>
          </Card>

          {/* CTA */}
          <div className="flex justify-center">
            <button
              onClick={() => router.push("/login")}
              className="animate-fade-in flex items-center gap-2 rounded-xl px-6 py-3.5 text-base font-semibold transition-opacity hover:opacity-85"
              style={{ background: "var(--color-nt-purple)", color: "#fff" }}
            >
              Sign in to view full dashboard
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
