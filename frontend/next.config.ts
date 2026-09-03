import type { NextConfig } from "next";

const backendApiBase = (
  process.env.BACKEND_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${backendApiBase}/:path*` }];
  },
};

export default nextConfig;
