import type { MetadataRoute } from "next";

// No public pages in v1: ask every crawler to stay out entirely.
export default function robots(): MetadataRoute.Robots {
  return { rules: { userAgent: "*", disallow: "/" } };
}
