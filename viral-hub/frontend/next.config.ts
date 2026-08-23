import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",   // necesario para Docker y Railway
  images: {
    remotePatterns: [
      { hostname: "*.r2.cloudflarestorage.com" },
      { hostname: "media.viralhub.io" },
      { hostname: "pbs.twimg.com" },
      { hostname: "yt3.ggpht.com" },
    ],
  },
  async rewrites() {
    // En dev: proxear /api/* al backend FastAPI
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
