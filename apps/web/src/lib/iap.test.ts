import { describe, expect, it } from "vitest";

import { IAP_ISSUER, IAP_KEYS_URL, iapKeyLookup, verifyIapAssertion } from "./iap";

const AUDIENCE = "/projects/123456/locations/us-central1/services/plytos-web";
const NOW = 1_800_000_000;

async function keyPair(): Promise<CryptoKeyPair> {
  return crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
}

function encode(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

async function assertion(
  key: CryptoKey,
  claims: Record<string, unknown> = {},
  header: Record<string, unknown> = {},
): Promise<string> {
  const head = encode({ alg: "ES256", kid: "k1", typ: "JWT", ...header });
  const body = encode({
    iss: IAP_ISSUER,
    aud: AUDIENCE,
    sub: "accounts.google.com:1234567890",
    email: "riley@example.com",
    iat: NOW - 5,
    exp: NOW + 595,
    ...claims,
  });
  const signature = await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" },
    key,
    new TextEncoder().encode(`${head}.${body}`),
  );
  return `${head}.${body}.${Buffer.from(signature).toString("base64url")}`;
}

describe("verifyIapAssertion", () => {
  it("names the person the proxy let in", async () => {
    const { privateKey, publicKey } = await keyPair();
    const keys = async (kid: string) => (kid === "k1" ? publicKey : null);
    const token = await assertion(privateKey);
    expect(await verifyIapAssertion(token, AUDIENCE, keys, NOW)).toEqual({
      sub: "accounts.google.com:1234567890",
      email: "riley@example.com",
    });
  });

  it("refuses anything not signed by the proxy, for this service, and current", async () => {
    const { privateKey, publicKey } = await keyPair();
    const other = await keyPair();
    const keys = async (kid: string) => (kid === "k1" ? publicKey : null);
    const refused = [
      await assertion(other.privateKey),
      await assertion(privateKey, { aud: "/projects/123456/locations/us-central1/services/elsewhere" }),
      await assertion(privateKey, { iss: "https://accounts.google.com" }),
      await assertion(privateKey, { exp: NOW - 120 }),
      await assertion(privateKey, { iat: NOW + 600 }),
      await assertion(privateKey, { sub: "" }),
      await assertion(privateKey, {}, { kid: "unknown" }),
      await assertion(privateKey, {}, { alg: "HS256" }),
      "not.an.assertion",
      "",
    ];
    for (const token of refused) {
      expect(await verifyIapAssertion(token, AUDIENCE, keys, NOW)).toBeNull();
    }
    // A payload changed after signing.
    const [head, , signature] = (await assertion(privateKey)).split(".");
    const forged = encode({ iss: IAP_ISSUER, aud: AUDIENCE, sub: "someone-else", iat: NOW, exp: NOW + 60 });
    expect(await verifyIapAssertion(`${head}.${forged}.${signature}`, AUDIENCE, keys, NOW)).toBeNull();
    // No audience configured means nobody is let in.
    expect(await verifyIapAssertion(await assertion(privateKey), "", keys, NOW)).toBeNull();
  });
});

describe("iapKeyLookup", () => {
  it("loads Google's keys once, and again only for a key it hasn't seen", async () => {
    const { privateKey, publicKey } = await keyPair();
    const jwk = { ...(await crypto.subtle.exportKey("jwk", publicKey)), kid: "k1" };
    const asked: string[] = [];
    const fetcher = (async (url: string) => {
      asked.push(url);
      return new Response(JSON.stringify({ keys: [jwk, { kty: "RSA", kid: "ignored" }] }));
    }) as unknown as typeof fetch;
    const lookup = iapKeyLookup(fetcher, () => 0);
    const token = await assertion(privateKey);
    expect(await verifyIapAssertion(token, AUDIENCE, lookup, NOW)).not.toBeNull();
    expect(await verifyIapAssertion(token, AUDIENCE, lookup, NOW)).not.toBeNull();
    expect(asked).toEqual([IAP_KEYS_URL]);
    expect(await lookup("rotated")).toBeNull();
    expect(asked).toHaveLength(2);
  });

  it("lets nobody in when Google's keys can't be fetched", async () => {
    const fetcher = (async () => new Response("down", { status: 503 })) as unknown as typeof fetch;
    expect(await iapKeyLookup(fetcher)("k1")).toBeNull();
  });
});
