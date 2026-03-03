import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: "https://foundry-backend.fly.dev/:path*",
      },
    ];
  },
};

export default nextConfig;
