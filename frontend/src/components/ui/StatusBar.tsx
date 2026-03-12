"use client";

import { useEffect, useState } from "react";

function isMarketOpen(): boolean {
  const now = new Date();
  const day = now.getUTCDay();
  if (day === 0 || day === 6) return false;
  const etHour = (now.getUTCHours() - 4 + 24) % 24;
  const etTime = etHour * 60 + now.getUTCMinutes();
  return etTime >= 9 * 60 + 30 && etTime < 16 * 60;
}

export default function StatusBar() {
  const [time, setTime] = useState("");
  const [marketOpen, setMarketOpen] = useState(false);

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      const pad = (n: number) => String(n).padStart(2, "0");
      setTime(`${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())}`);
      setMarketOpen(isMarketOpen());
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      className="fixed top-0 left-0 right-0 z-50 h-10 flex items-center justify-between px-6"
      style={{ backgroundColor: "#FFFFFF", borderBottom: "1px solid #D2D2D7" }}
    >
      {/* Left */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span
              className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
              style={{ backgroundColor: "#34C759" }}
            />
            <span
              className="relative inline-flex rounded-full h-2 w-2"
              style={{ backgroundColor: "#34C759" }}
            />
          </span>
          <span
            className="text-[10px] font-semibold tracking-[0.15em] uppercase"
            style={{ color: "#34C759" }}
          >
            SYSTEM ONLINE
          </span>
        </div>

        <span style={{ color: "#D2D2D7" }}>|</span>

        <div className="flex items-center gap-2">
          <span
            className="relative inline-flex rounded-full h-2 w-2"
            style={{ backgroundColor: marketOpen ? "#34C759" : "#FF3B30" }}
          />
          <span
            className="text-[10px] font-medium tracking-[0.1em] uppercase"
            style={{ color: marketOpen ? "#34C759" : "#6E6E73" }}
          >
            MARKET {marketOpen ? "OPEN" : "CLOSED"}
          </span>
        </div>
      </div>

      {/* Center */}
      <div
        className="text-[11px] font-semibold tracking-[0.2em] uppercase absolute left-1/2 -translate-x-1/2"
        style={{ color: "#1D1D1F" }}
      >
        NEWMAN TRADING SYSTEM v1.0
      </div>

      {/* Right */}
      <div className="flex items-center gap-2">
        <span
          className="text-xs font-mono tabular-nums"
          style={{ color: "#1D1D1F", fontVariantNumeric: "tabular-nums" }}
        >
          {time || "00:00:00"}
        </span>
        <span
          className="text-[10px] font-medium px-1.5 py-0.5 rounded"
          style={{ color: "#6E6E73", backgroundColor: "#F5F5F7", border: "1px solid #D2D2D7" }}
        >
          UTC
        </span>
      </div>
    </div>
  );
}
