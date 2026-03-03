"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

interface PublicStats {
  total_closed_trades: number;
  win_rate_pct: number;
  avg_hold_days: number;
  total_realized_pnl_pct: number;
  open_positions: number;
  system_status: string;
}

export default function HomePage() {
  const router = useRouter();
  const [stats, setStats] = useState<PublicStats | null>(null);
  const [loading, setLoading] = useState(true);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  useEffect(() => {
    fetch(`${apiUrl}/api/public/stats`)
      .then((r) => r.json())
      .then((data) => setStats(data))
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, [apiUrl]);

  const statusColor =
    stats?.system_status === "running"
      ? "#22c55e"
      : stats?.system_status === "paused"
      ? "#f59e0b"
      : "#6b7280";

  return (
    <main
      style={{
        minHeight: "100vh",
        backgroundColor: "#0a0a0f",
        color: "#f0f0f8",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
        fontFamily: "Inter, sans-serif",
      }}
    >
      {/* Header */}
      <div style={{ textAlign: "center", marginBottom: "3rem" }}>
        <h1
          style={{
            fontSize: "2.5rem",
            fontWeight: 700,
            letterSpacing: "-0.02em",
            marginBottom: "0.75rem",
            background: "linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Foundry
        </h1>
        <p style={{ color: "#94a3b8", fontSize: "1.1rem", maxWidth: "480px" }}>
          Sector-breakout trading — systematically identified, automatically executed.
        </p>
      </div>

      {/* Stats card */}
      <div
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: "1rem",
          padding: "2rem",
          width: "100%",
          maxWidth: "560px",
          marginBottom: "2rem",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1.5rem",
          }}
        >
          <h2 style={{ fontWeight: 600, fontSize: "1rem", color: "#94a3b8" }}>
            Live Performance
          </h2>
          {stats && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                fontSize: "0.75rem",
                fontWeight: 600,
                color: statusColor,
                background: `${statusColor}22`,
                border: `1px solid ${statusColor}44`,
                borderRadius: "9999px",
                padding: "0.2rem 0.75rem",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: statusColor,
                  display: "inline-block",
                }}
              />
              {stats.system_status}
            </span>
          )}
        </div>

        {loading ? (
          <p style={{ color: "#64748b", textAlign: "center", padding: "1rem 0" }}>
            Loading stats…
          </p>
        ) : !stats ? (
          <p style={{ color: "#64748b", textAlign: "center", padding: "1rem 0" }}>
            Stats unavailable
          </p>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "1.25rem",
            }}
          >
            {[
              {
                label: "Win Rate",
                value: `${stats.win_rate_pct.toFixed(1)}%`,
                positive: stats.win_rate_pct >= 50,
              },
              {
                label: "Total Return",
                value: `${stats.total_realized_pnl_pct >= 0 ? "+" : ""}${stats.total_realized_pnl_pct.toFixed(1)}%`,
                positive: stats.total_realized_pnl_pct >= 0,
              },
              {
                label: "Avg Hold",
                value: `${stats.avg_hold_days.toFixed(1)}d`,
                positive: null,
              },
              {
                label: "Closed Trades",
                value: stats.total_closed_trades.toString(),
                positive: null,
              },
              {
                label: "Open Positions",
                value: stats.open_positions.toString(),
                positive: null,
              },
            ].map(({ label, value, positive }) => (
              <div
                key={label}
                style={{
                  background: "rgba(255,255,255,0.03)",
                  borderRadius: "0.625rem",
                  padding: "1rem",
                  border: "1px solid rgba(255,255,255,0.06)",
                }}
              >
                <div
                  style={{
                    fontSize: "0.75rem",
                    color: "#64748b",
                    marginBottom: "0.375rem",
                    fontWeight: 500,
                  }}
                >
                  {label}
                </div>
                <div
                  style={{
                    fontSize: "1.5rem",
                    fontWeight: 700,
                    color:
                      positive === null
                        ? "#f0f0f8"
                        : positive
                        ? "#22c55e"
                        : "#ef4444",
                  }}
                >
                  {value}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sign in button */}
      <button
        onClick={() => router.push("/login")}
        style={{
          background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
          color: "#fff",
          border: "none",
          borderRadius: "0.625rem",
          padding: "0.875rem 2rem",
          fontSize: "0.95rem",
          fontWeight: 600,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          transition: "opacity 0.15s",
        }}
        onMouseOver={(e) => (e.currentTarget.style.opacity = "0.85")}
        onMouseOut={(e) => (e.currentTarget.style.opacity = "1")}
      >
        Sign in to view full dashboard  →
      </button>
    </main>
  );
}
