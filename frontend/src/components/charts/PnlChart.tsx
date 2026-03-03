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
import type { Position } from "@/lib/api";

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  const val = payload[0]?.value ?? 0;
  const isPos = val >= 0;
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
      <p
        style={{
          color: isPos ? "#00d4aa" : "#ff4d6d",
          fontSize: "12px",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        P&L: <strong>${val.toFixed(2)}</strong>
      </p>
    </div>
  );
};

export default function PnlChart({ positions }: { positions: Position[] }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const data = positions.map((p) => ({
    symbol: p.symbol,
    pnl: parseFloat((p.unrealized_pnl || 0).toFixed(2)),
  }));

  if (data.length === 0) {
    return (
      <div style={{ height: 192, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "#444466", fontSize: "13px" }}>No position data</span>
      </div>
    );
  }

  if (!mounted) return <div style={{ height: 192 }} />;

  return (
    <div style={{ height: 192 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 8, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" vertical={false} />
          <XAxis
            dataKey="symbol"
            tick={{ fill: "#8888aa", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis tick={{ fill: "#444466", fontSize: 10 }} axisLine={false} tickLine={false} />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <ReferenceLine y={0} stroke="#2a2a3e" />
          <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={index} fill={entry.pnl >= 0 ? "#00d4aa" : "#ff4d6d"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
