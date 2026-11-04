import type { NextConfig } from "next";

import { fileContentSecurityPolicy, securityHeaders } from "./src/lib/security-headers";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders({ dev: process.env.NODE_ENV !== "production" }),
      },
      // A later rule wins for the same header: the original file gets a
      // stricter policy that still lets the browser show a PDF.
      {
        source: "/import/:id/original",
        headers: [{ key: "Content-Security-Policy", value: fileContentSecurityPolicy() }],
      },
    ];
  },
};

export default nextConfig;
