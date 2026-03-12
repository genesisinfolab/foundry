import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms & Conditions — Foundry",
};

export default function TermsPage() {
  return (
    <div
      className="min-h-screen"
      style={{ backgroundColor: "var(--color-nt-bg)", color: "var(--color-nt-text)" }}
    >
      {/* Nav */}
      <nav
        className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4"
        style={{
          background: "rgba(255,255,255,0.9)",
          backdropFilter: "blur(12px)",
          borderBottom: "1px solid var(--color-nt-border)",
        }}
      >
        <Link
          href="/"
          className="text-sm font-medium transition-opacity hover:opacity-70"
          style={{ color: "var(--color-nt-secondary)", textDecoration: "none" }}
        >
          ← Foundry
        </Link>
      </nav>

      <main className="mx-auto max-w-2xl px-6 pt-28 pb-20">
        <h1
          className="mb-2 text-3xl font-bold"
          style={{ color: "var(--color-nt-text)" }}
        >
          Terms &amp; Conditions
        </h1>
        <p className="mb-10 text-sm" style={{ color: "var(--color-nt-secondary)" }}>
          Last updated: March 2026
        </p>

        <div className="space-y-8 text-sm leading-relaxed" style={{ color: "var(--color-nt-text)" }}>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">1. No Financial Advice</h2>
            <p style={{ color: "var(--color-nt-secondary)" }}>
              Foundry is a research and educational platform. Nothing on this site constitutes
              financial advice, investment advice, trading advice, or any other type of advice.
              All content is provided for informational and research purposes only. You should
              not make any financial or investment decision based on information presented here
              without consulting a qualified financial advisor.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">2. Paper Trading — Simulated Results Only</h2>
            <p style={{ color: "var(--color-nt-secondary)" }}>
              All trading activity shown on Foundry is paper trading — simulated trades executed
              with no real capital. Performance figures, equity curves, win rates, and all other
              statistics represent hypothetical results in a simulated environment. Simulated
              results do not represent actual trading and may not reflect the impact of material
              economic and market factors. Past simulated performance is not indicative of future
              results, whether simulated or real.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">3. Not a Registered Investment Advisor</h2>
            <p style={{ color: "var(--color-nt-secondary)" }}>
              Foundry is not a registered investment advisor, broker-dealer, or financial
              institution. We are not registered with the SEC, FINRA, or any other regulatory
              body. Use of this platform does not create a fiduciary relationship between you
              and Foundry.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">4. Waitlist and Early Access</h2>
            <p style={{ color: "var(--color-nt-secondary)" }}>
              Joining the waitlist does not guarantee access to any product or service. Waitlist
              submissions are used solely to gauge interest and notify potential users of platform
              availability. We will not share your email address with third parties without your
              explicit consent.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">5. Limitation of Liability</h2>
            <p style={{ color: "var(--color-nt-secondary)" }}>
              To the maximum extent permitted by law, Foundry and its operators shall not be
              liable for any direct, indirect, incidental, special, or consequential damages
              arising from your use of, or inability to use, this platform. This includes but
              is not limited to any trading losses, loss of data, or loss of profit.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">6. Intellectual Property</h2>
            <p style={{ color: "var(--color-nt-secondary)" }}>
              All strategy logic, code, research methodologies, and content on this platform
              are proprietary. You may not reproduce, distribute, or create derivative works
              from any content without express written permission.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">7. Changes to These Terms</h2>
            <p style={{ color: "var(--color-nt-secondary)" }}>
              We reserve the right to modify these terms at any time. Continued use of the
              platform after changes constitutes acceptance of the updated terms.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">8. Contact</h2>
            <p style={{ color: "var(--color-nt-secondary)" }}>
              Questions about these terms can be directed to{" "}
              <a
                href="mailto:info@genesis-analytics.io"
                style={{ color: "var(--color-nt-blue)" }}
              >
                info@genesis-analytics.io
              </a>
              .
            </p>
          </section>

        </div>
      </main>
    </div>
  );
}
