"use client";

import { useState } from "react";
import { CheckCircle2, XCircle, ChevronDown, ChevronRight } from "lucide-react";
import type { PipelineResult } from "@/lib/api";

interface Props {
  result: PipelineResult;
}

export default function PipelineResultComponent({ result }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const toggle = (i: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const steps = result.steps ?? [];

  return (
    <div
      className="rounded-xl p-5 animate-fade-in"
      style={{ backgroundColor: "#111118", border: "1px solid #1e1e2e" }}
    >
      <div className="flex items-center gap-3 mb-4">
        <span
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: "#00d4aa" }}
        >
          Pipeline Complete
        </span>
        <span
          className="text-[10px] px-2 py-0.5 rounded-full font-medium"
          style={{
            backgroundColor: "rgba(0,212,170,0.1)",
            color: "#00d4aa",
          }}
        >
          {steps.length} steps
        </span>
        <button
          className="ml-auto text-[11px] px-2 py-1 rounded transition-colors"
          style={{ color: "#444466", backgroundColor: "#16161f" }}
          onClick={() => setExpanded(new Set())}
        >
          Collapse all
        </button>
      </div>

      <div className="relative">
        {/* Vertical connector line */}
        <div
          className="absolute left-[7px] top-4 bottom-4 w-px"
          style={{ backgroundColor: "#1e1e2e" }}
        />

        <div className="space-y-1">
          {steps.map((step, i) => {
            const { step: name, status, error, ...rest } = step;
            const isErr = status === "error" || !!error;
            const isOpen = expanded.has(i);
            const hasDetails = Object.keys(rest).length > 0;

            return (
              <div key={i}>
                <div
                  className="flex items-center gap-3 py-2 px-3 rounded-lg cursor-pointer transition-colors"
                  style={{
                    backgroundColor: isOpen ? "#16161f" : "transparent",
                  }}
                  onClick={() => hasDetails && toggle(i)}
                >
                  <div className="relative z-10 flex-shrink-0">
                    {isErr ? (
                      <XCircle size={16} style={{ color: "#ff4d6d" }} />
                    ) : (
                      <CheckCircle2 size={16} style={{ color: "#00d4aa" }} />
                    )}
                  </div>

                  <span
                    className="flex-1 text-sm font-medium"
                    style={{ color: isErr ? "#ff4d6d" : "#f0f0f8" }}
                  >
                    {name}
                  </span>

                  {error && (
                    <span className="text-xs truncate max-w-xs" style={{ color: "#ff4d6d" }}>
                      {String(error)}
                    </span>
                  )}

                  {hasDetails &&
                    (isOpen ? (
                      <ChevronDown size={12} style={{ color: "#444466" }} />
                    ) : (
                      <ChevronRight size={12} style={{ color: "#444466" }} />
                    ))}
                </div>

                {isOpen && hasDetails && (
                  <div
                    className="ml-9 mb-2 p-3 rounded-lg"
                    style={{ backgroundColor: "#0d0d14", border: "1px solid #1e1e2e" }}
                  >
                    <pre
                      className="text-[11px]"
                      style={{ color: "#8888aa", whiteSpace: "pre-wrap", wordBreak: "break-word" }}
                    >
                      {JSON.stringify(rest, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
