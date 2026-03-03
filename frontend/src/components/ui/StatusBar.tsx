"use client";

import { useEffect, useState } from "react";

function isMarketOpen(): boolean {
  const now = new Date();
  const day = now.getUTCDay(); // 0 = Sun, 6 = Sat
  if (day === 0 || day === 6) return false;
  // Approximate ET as UTC-4 (EDT); off by 1h during EST — acceptable for display
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
      style={{ backgroundColor: "#0d0d14", borderBottom: "1px solid #1e1e2e" }}
    >
      {/* Left */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span
              className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
              style={{ backgroundColor: "#00d4aa" }}
            />
            <span
              className="relative inline-flex rounded-full h-2 w-2"
              style={{ backgroundColor: "#00d4aa" }}
            />
          </span>
          <span
            className="text-[10px] font-semibold tracking-[0.15em] uppercase"
            style={{ color: "#00d4aa" }}
          >
            SYSTEM ONLINE
          </span>
        </div>

        <span style={{ color: "#2a2a3e" }}>|</span>

        <div className="flex items-center gap-2">
          <span
            className="relative inline-flex rounded-full h-2 w-2"
            style={{
              backgroundColor: marketOpen ? "#00d4aa" : "#ff4d6d",
              boxShadow: marketOpen ? "0 0 6px rgba(0,212,170,0.6)" : "none",
            }}
          />
          <span
            className="text-[10px] font-medium tracking-[0.1em] uppercase"
            style={{ color: marketOpen ? "#00d4aa" : "#8888aa" }}
          >
            MARKET {marketOpen ? "OPEN" : "CLOSED"}
          </span>
        </div>
      </div>

      {/* Center */}
      <div
        className="text-[11px] font-semibold tracking-[0.2em] uppercase absolute left-1/2 -translate-x-1/2"
        style={{ color: "#f0f0f8" }}
      >
        NEWMAN TRADING SYSTEM v1.0
      </div>

      {/* Right */}
      <div className="flex items-center gap-2">
        <span
          className="text-xs font-mono tabular-nums"
          style={{ color: "#f0f0f8", fontVariantNumeric: "tabular-nums" }}
        >
          {time || "00:00:00"}
        </span>
        <span
          className="text-[10px] font-medium px-1.5 py-0.5 rounded"
          style={{ color: "#8888aa", backgroundColor: "#1e1e2e" }}
        >
          UTC
        </span>
      </div>
    </div>
  );
}
