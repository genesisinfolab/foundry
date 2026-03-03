"use client";

import { useState, useEffect } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import type { Theme } from "@/lib/api";

const STATUS_COLORS: Record<string, string> = {
  hot: "#ff4d6d",
  emerging: "#fbbf24",
  cooling: "#4d9fff",
  dead: "#444466",
};

const CustomTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { name: string; value: number; payload: { fill: string } }[];
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        backgroundColor: "#111118",
        border: "1px solid #2a2a3e",
        borderRadius: "6px",
        padding: "8px 12px",
      }}
    >
      <p
        style={{
          color: payload[0]?.payload?.fill,
          fontSize: "12px",
          fontWeight: 600,
        }}
      >
        {payload[0]?.name}: {payload[0]?.value}
      </p>
    </div>
  );
};

export default function ThemeDistribution({ themes }: { themes: Theme[] }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const counts = themes.reduce<Record<string, number>>((acc, t) => {
    acc[t.status] = (acc[t.status] ?? 0) + 1;
    return acc;
  }, {});

  const data = Object.entries(counts)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1),
      value,
      fill: STATUS_COLORS[name] ?? "#444466",
    }));

  if (data.length === 0) {
    return (
      <div style={{ height: 72, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "#444466", fontSize: "12px" }}>No themes yet</span>
      </div>
    );
  }

  if (!mounted) return <div style={{ height: 72, marginTop: 8 }} />;

  return (
    <div style={{ height: 72, marginTop: 8 }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={20}
            outerRadius={30}
            paddingAngle={2}
            dataKey="value"
            startAngle={90}
            endAngle={-270}
          >
            {data.map((entry, index) => (
              <Cell key={index} fill={entry.fill} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: "10px", color: "#8888aa" }}
            iconSize={7}
            iconType="circle"
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
