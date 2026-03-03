"use client";

import { useState, useEffect } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { WatchlistItem } from "@/lib/api";

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { value: number; fill: string }[];
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  const val = payload[0]?.value;
  const fill = payload[0]?.fill;
  return (
    <div
      style={{
        backgroundColor: "#111118",
        border: "1px solid #2a2a3e",
        borderRadius: "8px",
        padding: "10px 14px",
      }}
    >
      <p style={{ color: "#f0f0f8", fontSize: "13px", fontWeight: 600, marginBottom: "4px" }}>
        {label}
      </p>
      <p style={{ color: fill, fontSize: "12px", fontVariantNumeric: "tabular-nums" }}>
        Vol Ratio: <strong>{val?.toFixed(1)}x</strong>
      </p>
    </div>
  );
};

export default function VolumeRatioChart({ watchlist }: { watchlist: WatchlistItem[] }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const data = watchlist
    .filter((w) => w.volume_ratio != null)
    .sort((a, b) => (b.volume_ratio ?? 0) - (a.volume_ratio ?? 0))
    .slice(0, 20)
    .map((w) => ({
      symbol: w.symbol,
      ratio: parseFloat((w.volume_ratio ?? 0).toFixed(2)),
      near_breakout: w.near_breakout,
    }));

  if (data.length === 0) {
    return (
      <div style={{ height: 192, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "#444466", fontSize: "13px" }}>No watchlist data — run the pipeline</span>
      </div>
    );
  }

  if (!mounted) return <div style={{ height: 192 }} />;

  return (
    <div style={{ height: 192 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" vertical={false} />
          <XAxis
            dataKey="symbol"
            tick={{ fill: "#8888aa", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#444466", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <ReferenceLine y={1} stroke="#2a2a3e" strokeDasharray="4 4" />
          <Bar dataKey="ratio" radius={[3, 3, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={index} fill={entry.near_breakout ? "#00d4aa" : "#fbbf24"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
