"use client";

import { useState, useEffect } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { Theme } from "@/lib/api";

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { color: string; name: string; value: number }[];
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        backgroundColor: "#111118",
        border: "1px solid #2a2a3e",
        borderRadius: "8px",
        padding: "10px 14px",
        backdropFilter: "blur(8px)",
      }}
    >
      <p style={{ color: "#8888aa", fontSize: "11px", marginBottom: "6px" }}>{label}</p>
      {payload.map((entry, i) => (
        <p
          key={i}
          style={{ color: entry.color, fontSize: "12px", fontVariantNumeric: "tabular-nums" }}
        >
          {entry.name}:{" "}
          <strong>{typeof entry.value === "number" ? entry.value.toFixed(2) : entry.value}</strong>
        </p>
      ))}
    </div>
  );
};

export default function ThemeScoreChart({ themes }: { themes: Theme[] }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const data = [...themes]
    .sort((a, b) => b.score - a.score)
    .slice(0, 8)
    .map((t) => ({
      name: t.name.length > 20 ? t.name.slice(0, 20) + "…" : t.name,
      News: parseFloat((t.news_score || 0).toFixed(2)),
      Social: parseFloat((t.social_score || 0).toFixed(2)),
      ETF: parseFloat((t.etf_score || 0).toFixed(2)),
    }));

  if (data.length === 0) {
    return (
      <div style={{ height: 224, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "#444466", fontSize: "13px" }}>No theme data — run the pipeline to scan</span>
      </div>
    );
  }

  if (!mounted) return <div style={{ height: 224 }} />;

  return (
    <div style={{ height: 224 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 48, left: 8, bottom: 4 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: "#444466", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fill: "#8888aa", fontSize: 11 }}
            width={140}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <Legend
            wrapperStyle={{ fontSize: "11px", color: "#8888aa", paddingTop: "8px" }}
            iconSize={8}
            iconType="square"
          />
          <Bar dataKey="News" stackId="a" fill="#4d9fff" />
          <Bar dataKey="Social" stackId="a" fill="#a78bfa" />
          <Bar dataKey="ETF" stackId="a" fill="#fbbf24" radius={[0, 3, 3, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
