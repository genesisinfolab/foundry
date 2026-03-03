"use client";

import { type LucideIcon } from "lucide-react";

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string;
  delta?: string;
  positive?: boolean;
  negative?: boolean;
  borderColor?: "green" | "blue" | "red" | "amber";
}

const BORDER_COLORS = {
  green: "#00d4aa",
  blue: "#4d9fff",
  red: "#ff4d6d",
  amber: "#fbbf24",
};

export default function StatCard({
  icon: Icon,
  label,
  value,
  delta,
  positive,
  negative,
  borderColor = "green",
}: StatCardProps) {
  const bc = BORDER_COLORS[borderColor];

  return (
    <div
      className="relative rounded-xl p-4 transition-all duration-200 cursor-default group"
      style={{
        background: "linear-gradient(to bottom, #16161f, #111118)",
        borderTop: "1px solid #1e1e2e",
        borderRight: "1px solid #1e1e2e",
        borderBottom: "1px solid #1e1e2e",
        borderLeft: `3px solid ${bc}`,
      }}
      onMouseEnter={(e) => {
        const el = e.currentTarget as HTMLDivElement;
        el.style.boxShadow = "0 0 0 1px rgba(0,212,170,0.15), 0 8px 32px rgba(0,0,0,0.4)";
        el.style.borderTopColor = "#2a2a3e";
        el.style.borderRightColor = "#2a2a3e";
        el.style.borderBottomColor = "#2a2a3e";
      }}
      onMouseLeave={(e) => {
        const el = e.currentTarget as HTMLDivElement;
        el.style.boxShadow = "none";
        el.style.borderTopColor = "#1e1e2e";
        el.style.borderRightColor = "#1e1e2e";
        el.style.borderBottomColor = "#1e1e2e";
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon size={13} style={{ color: bc }} />
        <span
          className="text-[10px] font-semibold uppercase tracking-[0.12em]"
          style={{ color: "#444466" }}
        >
          {label}
        </span>
      </div>
      <div
        className="text-xl font-bold tabular-nums"
        style={{
          color: positive ? "#00d4aa" : negative ? "#ff4d6d" : "#f0f0f8",
          textShadow: positive
            ? "0 0 12px rgba(0,212,170,0.3)"
            : negative
            ? "0 0 12px rgba(255,77,109,0.25)"
            : "none",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
      {delta && (
        <div className="text-[11px] mt-1" style={{ color: "#8888aa" }}>
          {delta}
        </div>
      )}
    </div>
  );
}
