import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Foundry",
  description: "Sector-breakout trading — systematically identified, automatically executed.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} min-h-screen`} style={{ backgroundColor: '#0a0a0f', color: '#f0f0f8' }}>
        {children}
      </body>
    </html>
  );
}
