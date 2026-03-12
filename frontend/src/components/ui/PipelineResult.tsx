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
      style={{ backgroundColor: "#FFFFFF", border: "1px solid #D2D2D7" }}
    >
      <div className="flex items-center gap-3 mb-4">
        <span
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: "#34C759" }}
        >
          Pipeline Complete
        </span>
        <span
          className="text-[10px] px-2 py-0.5 rounded-full font-medium"
          style={{
            backgroundColor: "rgba(52,199,89,0.1)",
            color: "#34C759",
          }}
        >
          {steps.length} steps
        </span>
        <button
          className="ml-auto text-[11px] px-2 py-1 rounded transition-opacity hover:opacity-70"
          style={{ color: "#6E6E73", backgroundColor: "#F5F5F7", border: "1px solid #D2D2D7" }}
          onClick={() => setExpanded(new Set())}
        >
          Collapse all
        </button>
      </div>

      <div className="relative">
        <div
          className="absolute left-[7px] top-4 bottom-4 w-px"
          style={{ backgroundColor: "#D2D2D7" }}
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
                  style={{ backgroundColor: isOpen ? "#F5F5F7" : "transparent" }}
                  onClick={() => hasDetails && toggle(i)}
                >
                  <div className="relative z-10 flex-shrink-0">
                    {isErr ? (
                      <XCircle size={16} style={{ color: "#FF3B30" }} />
                    ) : (
                      <CheckCircle2 size={16} style={{ color: "#34C759" }} />
                    )}
                  </div>

                  <span
                    className="flex-1 text-sm font-medium"
                    style={{ color: isErr ? "#FF3B30" : "#1D1D1F" }}
                  >
                    {name}
                  </span>

                  {error && (
                    <span className="text-xs truncate max-w-xs" style={{ color: "#FF3B30" }}>
                      {String(error)}
                    </span>
                  )}

                  {hasDetails &&
                    (isOpen ? (
                      <ChevronDown size={12} style={{ color: "#C7C7CC" }} />
                    ) : (
                      <ChevronRight size={12} style={{ color: "#C7C7CC" }} />
                    ))}
                </div>

                {isOpen && hasDetails && (
                  <div
                    className="ml-9 mb-2 p-3 rounded-lg"
                    style={{ backgroundColor: "#F5F5F7", border: "1px solid #D2D2D7" }}
                  >
                    <pre
                      className="text-[11px]"
                      style={{ color: "#6E6E73", whiteSpace: "pre-wrap", wordBreak: "break-word" }}
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
