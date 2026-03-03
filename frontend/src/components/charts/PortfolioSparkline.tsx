"use client";

import { useMemo, useState, useEffect } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const CustomTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { value: number; payload: { date: string } }[];
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        backgroundColor: "#111118",
        border: "1px solid #2a2a3e",
        borderRadius: "6px",
        padding: "8px 12px",
        fontSize: "11px",
      }}
    >
      <p style={{ color: "#8888aa", marginBottom: "2px" }}>{payload[0]?.payload?.date}</p>
      <p
        style={{
          color: "#00d4aa",
          fontVariantNumeric: "tabular-nums",
          fontWeight: 600,
        }}
      >
        ${payload[0]?.value?.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
      </p>
    </div>
  );
};

export default function PortfolioSparkline({ equity }: { equity: number | undefined }) {
  const data = useMemo(() => {
    const base = equity || 100_000;
    // Seeded pseudo-random for stable, deterministic rendering
    let rng = (Math.floor(base) & 0x7fffffff) || 1;
    const next = () => {
      rng = ((rng * 1664525 + 1013904223) | 0) >>> 0;
      return rng / 0xffffffff;
    };

    let current = base * 0.96;
    const points = [];
    for (let i = 29; i >= 0; i--) {
      current *= 1 + (next() - 0.48) * 0.018;
      const d = new Date();
      d.setDate(d.getDate() - i);
      points.push({
        date: d.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        value: Math.round(current),
      });
    }
    // Anchor last point to actual equity
    if (points.length > 0) points[points.length - 1].value = Math.round(base);
    return points;
  }, [equity]);

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const vals = data.map((d) => d.value);
  const minVal = Math.min(...vals);
  const maxVal = Math.max(...vals);

  if (!mounted) return <div style={{ height: 72, marginTop: 8 }} />;

  return (
    <div style={{ height: 72, marginTop: 8 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 0 }}>
          <defs>
            <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#00d4aa" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#00d4aa" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" hide />
          <YAxis domain={[minVal * 0.995, maxVal * 1.005]} hide />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#00d4aa"
            strokeWidth={1.5}
            fill="url(#portfolioGrad)"
            dot={false}
            activeDot={{ r: 3, fill: "#00d4aa", strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
