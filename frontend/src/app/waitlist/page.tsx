"use client";

import { useState } from "react";
import Link from "next/link";

export default function WaitlistPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(true);
  }

  return (
    <div
      className="min-h-screen"
      style={{ backgroundColor: "var(--color-nt-bg)", color: "var(--color-nt-text)" }}
    >
      {/* Nav */}
      <nav
        className="fixed top-0 left-0 right-0 z-50 flex items-center px-6 py-4"
        style={{
          background: "rgba(255,255,255,0.9)",
          backdropFilter: "blur(12px)",
          borderBottom: "1px solid var(--color-nt-border)",
        }}
      >
        <Link
          href="/"
          className="text-sm font-semibold transition-opacity hover:opacity-70"
          style={{ color: "#AEAEB2", textDecoration: "none" }}
        >
          Foundry
        </Link>
      </nav>

      <main className="mx-auto max-w-md px-6 pt-40 pb-20 flex flex-col items-center text-center gap-8">
        {/* Badge */}
        <span
          className="rounded-full px-3 py-1 text-xs font-semibold"
          style={{
            background: "color-mix(in srgb, var(--color-nt-purple) 12%, transparent)",
            color: "var(--color-nt-purple)",
            border: "1px solid color-mix(in srgb, var(--color-nt-purple) 25%, transparent)",
          }}
        >
          Private Beta
        </span>

        {/* Heading */}
        <div className="space-y-3">
          <h1 className="text-3xl font-bold" style={{ color: "var(--color-nt-text)" }}>
            Foundry is invite-only
          </h1>
          <p className="text-sm leading-relaxed" style={{ color: "var(--color-nt-secondary)" }}>
            We&apos;re running a closed beta while we refine the platform.
            Leave your email and we&apos;ll reach out when a spot opens up.
          </p>
        </div>

        {/* Form */}
        <div
          className="w-full rounded-2xl p-6 space-y-4"
          style={{
            backgroundColor: "var(--color-nt-surface)",
            border: "1px solid var(--color-nt-border)",
          }}
        >
          {submitted ? (
            <div className="py-4 space-y-2">
              <p className="text-2xl">✓</p>
              <p className="font-semibold" style={{ color: "var(--color-nt-green)" }}>
                You&apos;re on the list
              </p>
              <p className="text-sm" style={{ color: "var(--color-nt-secondary)" }}>
                We&apos;ll email you at <strong>{email}</strong> when a spot opens.
              </p>
            </div>
          ) : (
            <>
              <p className="text-sm font-medium text-left" style={{ color: "var(--color-nt-secondary)" }}>
                Request early access
              </p>
              <form onSubmit={handleSubmit} className="flex flex-col gap-3">
                <input
                  type="email"
                  required
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-lg px-3 py-2.5 text-sm outline-none"
                  style={{
                    backgroundColor: "var(--color-nt-elevated)",
                    border: "1px solid var(--color-nt-border-accent)",
                    color: "var(--color-nt-text)",
                  }}
                  onFocus={(e) => (e.target.style.borderColor = "var(--color-nt-blue)")}
                  onBlur={(e) => (e.target.style.borderColor = "var(--color-nt-border-accent)")}
                />
                <button
                  type="submit"
                  className="w-full rounded-lg py-2.5 text-sm font-semibold transition-opacity hover:opacity-85"
                  style={{ backgroundColor: "var(--color-nt-blue)", color: "#fff" }}
                >
                  Join the waitlist
                </button>
              </form>
            </>
          )}
        </div>

        {/* Footer note */}
        <p className="text-xs" style={{ color: "var(--color-nt-secondary)" }}>
          No spam. We won&apos;t share your email with anyone.
        </p>

        {/* Back link */}
        <Link
          href="/"
          className="text-sm transition-opacity hover:opacity-70"
          style={{ color: "var(--color-nt-blue)", textDecoration: "none" }}
        >
          ← Back to Foundry
        </Link>
      </main>
    </div>
  );
}
