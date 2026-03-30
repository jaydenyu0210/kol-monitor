import type { NextConfig } from "next";

// Use 127.0.0.1 explicitly to avoid IPv6 resolution issues with Docker Desktop on Mac
const BACKEND_URL = process.env.BACKEND_PROXY_URL || process.env.NEXT_PUBLIC_RAILWAY_API_URL?.replace('localhost', '127.0.0.1') || 'http://127.0.0.1:3001'

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ]
  },
};

export default nextConfig;
