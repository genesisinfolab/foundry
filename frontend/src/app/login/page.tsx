"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setError(error.message);
      setLoading(false);
    } else {
      router.push("/dashboard");
    }
  }

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4"
      style={{ backgroundColor: "var(--color-nt-bg)", color: "var(--color-nt-text)" }}
    >
      {/* Back to home */}
      <a
        href="/"
        className="fixed top-6 left-6 text-sm font-medium transition-opacity hover:opacity-70"
        style={{ color: "var(--color-nt-secondary)" }}
      >
        ← Foundry
      </a>

      <Card
        className="w-full max-w-sm"
        style={{
          backgroundColor: "var(--color-nt-surface)",
          borderColor: "var(--color-nt-border)",
        }}
      >
        <CardHeader>
          <CardTitle className="text-xl font-bold" style={{ color: "var(--color-nt-purple)" }}>
            Sign in
          </CardTitle>
          <CardDescription style={{ color: "var(--color-nt-secondary)" }}>
            Access the Foundry dashboard
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium" style={{ color: "var(--color-nt-secondary)" }}>
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-colors focus:ring-1"
                style={{
                  backgroundColor: "var(--color-nt-elevated)",
                  border: "1px solid var(--color-nt-border-accent)",
                  color: "var(--color-nt-text)",
                  boxSizing: "border-box",
                }}
                onFocus={(e) => (e.target.style.borderColor = "var(--color-nt-purple)")}
                onBlur={(e) => (e.target.style.borderColor = "var(--color-nt-border-accent)")}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium" style={{ color: "var(--color-nt-secondary)" }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-colors"
                style={{
                  backgroundColor: "var(--color-nt-elevated)",
                  border: "1px solid var(--color-nt-border-accent)",
                  color: "var(--color-nt-text)",
                  boxSizing: "border-box",
                }}
                onFocus={(e) => (e.target.style.borderColor = "var(--color-nt-purple)")}
                onBlur={(e) => (e.target.style.borderColor = "var(--color-nt-border-accent)")}
              />
            </div>

            {error && (
              <p
                className="rounded-lg px-3 py-2 text-sm"
                style={{
                  color: "var(--color-nt-red)",
                  backgroundColor: "color-mix(in srgb, var(--color-nt-red) 12%, transparent)",
                  border: "1px solid color-mix(in srgb, var(--color-nt-red) 25%, transparent)",
                }}
              >
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="mt-2 w-full rounded-lg py-2.5 text-sm font-semibold transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-60"
              style={{ backgroundColor: "var(--color-nt-purple)", color: "#fff" }}
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
