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
        stripe: "#ff4d6d",
        bg: "rgba(255,77,109,0.06)",
        border: "rgba(255,77,109,0.25)",
      };
    case "warning":
      return {
        stripe: "#fbbf24",
        bg: "rgba(251,191,36,0.06)",
        border: "rgba(251,191,36,0.25)",
      };
    default:
      return {
        stripe: "#4d9fff",
        bg: "rgba(77,159,255,0.06)",
        border: "rgba(77,159,255,0.25)",
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
        borderTop: `1px solid ${alert.acknowledged ? "#1e1e2e" : styles.border}`,
        borderRight: `1px solid ${alert.acknowledged ? "#1e1e2e" : styles.border}`,
        borderBottom: `1px solid ${alert.acknowledged ? "#1e1e2e" : styles.border}`,
        borderLeft: `3px solid ${styles.stripe}`,
        opacity: alert.acknowledged ? 0.45 : 1,
        boxShadow: !alert.acknowledged
          ? `0 0 0 1px ${styles.border} inset`
          : "none",
      }}
    >
      <div className="flex-shrink-0 mt-0.5">
        <Icon size={15} style={{ color: styles.stripe }} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2 mb-1">
          <span className="font-semibold text-sm" style={{ color: "#f0f0f8" }}>
            {alert.title}
          </span>
          <span
            className="text-[11px] flex-shrink-0 tabular-nums"
            style={{ color: "#444466", fontVariantNumeric: "tabular-nums" }}
          >
            {timeAgo}
          </span>
        </div>

        <p
          className="text-xs leading-relaxed whitespace-pre-wrap"
          style={{ color: "#8888aa" }}
        >
          {alert.message}
        </p>

        {alert.symbol && (
          <span
            className="inline-block mt-2 text-[10px] px-2 py-0.5 rounded font-mono font-semibold"
            style={{ backgroundColor: "#1e1e2e", color: "#4d9fff" }}
          >
            {alert.symbol}
          </span>
        )}
      </div>

      {!alert.acknowledged && (
        <button
          onClick={() => onAck(alert.id)}
          className="flex-shrink-0 self-start flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-md transition-colors"
          style={{ color: "#8888aa", backgroundColor: "#1e1e2e" }}
          onMouseEnter={(e) => {
            const el = e.currentTarget as HTMLButtonElement;
            el.style.color = "#f0f0f8";
            el.style.backgroundColor = "#2a2a3e";
          }}
          onMouseLeave={(e) => {
            const el = e.currentTarget as HTMLButtonElement;
            el.style.color = "#8888aa";
            el.style.backgroundColor = "#1e1e2e";
          }}
        >
          <Check size={10} />
          Read
        </button>
      )}
    </div>
  );
}
