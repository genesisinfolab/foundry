"use client";

import { formatDistanceToNow } from "date-fns";
import {
  AlertCircle,
  AlertTriangle,
  Info,
  Zap,
  ShieldAlert,
  Check,
} from "lucide-react";
import type { AlertItem } from "@/lib/api";

interface AlertCardProps {
  alert: AlertItem;
  onAck: (id: number) => void;
}

function getSeverityStyles(severity: string) {
  switch (severity) {
    case "critical":
    case "action":
      return {
        stripe: "#FF3B30",
        bg: "rgba(255,59,48,0.05)",
        border: "rgba(255,59,48,0.2)",
      };
    case "warning":
      return {
        stripe: "#FF9500",
        bg: "rgba(255,149,0,0.05)",
        border: "rgba(255,149,0,0.2)",
      };
    default:
      return {
        stripe: "#0066CC",
        bg: "rgba(0,102,204,0.05)",
        border: "rgba(0,102,204,0.2)",
      };
  }
}

function getIcon(type: string, severity: string) {
  if (type.includes("breakout") || type.includes("entry")) return Zap;
  if (type.includes("stop")) return ShieldAlert;
  if (severity === "critical" || severity === "action") return AlertCircle;
  if (severity === "warning") return AlertTriangle;
  return Info;
}

export default function AlertCard({ alert, onAck }: AlertCardProps) {
  const styles = getSeverityStyles(alert.severity);
  const Icon = getIcon(alert.type, alert.severity);

  const timeAgo = alert.created_at
    ? formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })
    : "";

  return (
    <div
      className="relative flex gap-3 rounded-xl p-4 transition-all duration-200 animate-slide-in"
      style={{
        backgroundColor: alert.acknowledged ? "transparent" : styles.bg,
        borderTop: `1px solid ${alert.acknowledged ? "#D2D2D7" : styles.border}`,
        borderRight: `1px solid ${alert.acknowledged ? "#D2D2D7" : styles.border}`,
        borderBottom: `1px solid ${alert.acknowledged ? "#D2D2D7" : styles.border}`,
        borderLeft: `3px solid ${styles.stripe}`,
        opacity: alert.acknowledged ? 0.45 : 1,
      }}
    >
      <div className="flex-shrink-0 mt-0.5">
        <Icon size={15} style={{ color: styles.stripe }} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2 mb-1">
          <span className="font-semibold text-sm" style={{ color: "#1D1D1F" }}>
            {alert.title}
          </span>
          <span
            className="text-[11px] flex-shrink-0 tabular-nums"
            style={{ color: "#C7C7CC", fontVariantNumeric: "tabular-nums" }}
          >
            {timeAgo}
          </span>
        </div>

        <p
          className="text-xs leading-relaxed whitespace-pre-wrap"
          style={{ color: "#6E6E73" }}
        >
          {alert.message}
        </p>

        {alert.symbol && (
          <span
            className="inline-block mt-2 text-[10px] px-2 py-0.5 rounded font-mono font-semibold"
            style={{ backgroundColor: "#F5F5F7", border: "1px solid #D2D2D7", color: "#0066CC" }}
          >
            {alert.symbol}
          </span>
        )}
      </div>

      {!alert.acknowledged && (
        <button
          onClick={() => onAck(alert.id)}
          className="flex-shrink-0 self-start flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-md transition-opacity hover:opacity-70"
          style={{ color: "#6E6E73", backgroundColor: "#F5F5F7", border: "1px solid #D2D2D7" }}
        >
          <Check size={10} />
          Read
        </button>
      )}
    </div>
  );
}
