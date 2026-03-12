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
  green: "#34C759",
  blue: "#0066CC",
  red: "#FF3B30",
  amber: "#FF9500",
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
      className="relative rounded-xl p-4 transition-all duration-200 cursor-default"
      style={{
        backgroundColor: "#FFFFFF",
        borderTop: "1px solid #D2D2D7",
        borderRight: "1px solid #D2D2D7",
        borderBottom: "1px solid #D2D2D7",
        borderLeft: `3px solid ${bc}`,
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.backgroundColor = "#F5F5F7";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.backgroundColor = "#FFFFFF";
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon size={13} style={{ color: bc }} />
        <span
          className="text-[10px] font-semibold uppercase tracking-[0.12em]"
          style={{ color: "#6E6E73" }}
        >
          {label}
        </span>
      </div>
      <div
        className="text-xl font-bold tabular-nums"
        style={{
          color: positive ? "#34C759" : negative ? "#FF3B30" : "#1D1D1F",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
      {delta && (
        <div className="text-[11px] mt-1" style={{ color: "#6E6E73" }}>
          {delta}
        </div>
      )}
    </div>
  );
}
