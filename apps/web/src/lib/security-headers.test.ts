import { describe, expect, it } from "vitest";

import robots from "../app/robots";
import { contentSecurityPolicy, securityHeaders } from "./security-headers";

function header(name: string, dev = false): string | undefined {
  return securityHeaders({ dev }).find((h) => h.key === name)?.value;
}

describe("privacy headers", () => {
  it("tells every crawler not to index, follow or archive", () => {
    expect(header("X-Robots-Tag")).toContain("noindex");
    expect(header("X-Robots-Tag")).toContain("nofollow");
    expect(header("X-Robots-Tag")).toContain("noarchive");
  });

  it("never sends a referrer and can't be framed", () => {
    expect(header("Referrer-Policy")).toBe("no-referrer");
    expect(header("X-Frame-Options")).toBe("DENY");
    expect(contentSecurityPolicy({ dev: false })).toContain("frame-ancestors 'none'");
  });

  it("allows eval only in development", () => {
    expect(contentSecurityPolicy({ dev: false })).not.toContain("unsafe-eval");
    expect(contentSecurityPolicy({ dev: true })).toContain("unsafe-eval");
  });

  it("disallows the whole site in robots.txt", () => {
    expect(robots().rules).toEqual({ userAgent: "*", disallow: "/" });
  });
});
