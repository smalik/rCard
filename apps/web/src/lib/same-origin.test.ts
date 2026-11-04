import { describe, expect, it } from "vitest";

import { isSameOrigin } from "./same-origin";

describe("isSameOrigin", () => {
  const request = (headers: Record<string, string>) =>
    new Request("http://localhost:3000/import/upload", { method: "POST", headers });

  it("accepts Plytos's own pages", () => {
    expect(isSameOrigin(request({ "sec-fetch-site": "same-origin" }))).toBe(true);
    expect(isSameOrigin(request({ origin: "http://localhost:3000", host: "localhost:3000" }))).toBe(
      true,
    );
  });

  it("refuses other sites and requests that don't say where they came from", () => {
    expect(isSameOrigin(request({ "sec-fetch-site": "cross-site" }))).toBe(false);
    expect(isSameOrigin(request({ origin: "https://evil.example", host: "localhost:3000" }))).toBe(
      false,
    );
    expect(isSameOrigin(request({}))).toBe(false);
  });
});
