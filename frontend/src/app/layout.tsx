import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const protoMono = localFont({
  src: "../../public/fonts/ProtoMono-Regular.otf",
  variable: "--font-proto-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Foundry",
  description: "Sector-breakout trading — systematically identified, automatically executed.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={protoMono.variable}>
      <body
        className="min-h-screen"
        style={{
          backgroundColor: "#F5F5F7",
          color: "#1D1D1F",
          fontFamily: "var(--font-proto-mono), 'SF Mono', 'Fira Code', 'Consolas', monospace",
        }}
      >
        {children}
      </body>
    </html>
  );
}
