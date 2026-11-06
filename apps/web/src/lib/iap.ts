// Google's Identity-Aware Proxy sits in front of the web app on Cloud Run and
// signs an assertion naming the person on every request it lets through. The
// web app checks that signature itself rather than trusting plain headers, so
// a request that somehow skipped the proxy can't claim to be anyone.
//
// https://cloud.google.com/iap/docs/signed-headers-howto

export const IAP_ASSERTION_HEADER = "x-goog-iap-jwt-assertion";
export const IAP_KEYS_URL = "https://www.gstatic.com/iap/verify/public_key-jwk";
export const IAP_ISSUER = "https://cloud.google.com/iap";

// Allowed difference between Google's clock and ours, in seconds.
const SKEW_SECONDS = 60;
// The keys rotate now and then; a fresh copy is fetched at most this often,
// or sooner when an assertion names a key we haven't seen.
const KEYS_TTL_MS = 60 * 60 * 1000;

export type IapIdentity = { sub: string; email: string };
export type KeyLookup = (kid: string) => Promise<CryptoKey | null>;

function decode(part: string): Uint8Array<ArrayBuffer> {
  return new Uint8Array(Buffer.from(part, "base64url"));
}

function decodeJson(part: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(Buffer.from(part, "base64url").toString("utf8"));
    return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

// The person an assertion names, or null unless it is signed by one of
// Google's IAP keys, meant for this service, from IAP, and current.
export async function verifyIapAssertion(
  assertion: string,
  audience: string,
  keyFor: KeyLookup,
  nowSeconds: number = Date.now() / 1000,
): Promise<IapIdentity | null> {
  const parts = assertion.split(".");
  const [head, body, signature] = parts;
  if (parts.length !== 3 || head === undefined || body === undefined || signature === undefined || !audience) {
    return null;
  }
  const header = decodeJson(head);
  if (!header || header.alg !== "ES256" || typeof header.kid !== "string") return null;
  const key = await keyFor(header.kid);
  if (!key) return null;
  const signed = new TextEncoder().encode(`${head}.${body}`);
  let valid = false;
  try {
    valid = await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, key, decode(signature), signed);
  } catch {
    return null;
  }
  if (!valid) return null;

  const claims = decodeJson(body);
  if (!claims || claims.iss !== IAP_ISSUER) return null;
  const audiences = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!audiences.includes(audience)) return null;
  if (typeof claims.exp !== "number" || claims.exp < nowSeconds - SKEW_SECONDS) return null;
  if (typeof claims.iat !== "number" || claims.iat > nowSeconds + SKEW_SECONDS) return null;
  if (typeof claims.sub !== "string" || !claims.sub) return null;
  return { sub: claims.sub, email: typeof claims.email === "string" ? claims.email : "" };
}

type KeySet = { keys: Map<string, CryptoKey>; fetchedAt: number };

async function fetchKeys(fetcher: typeof fetch): Promise<Map<string, CryptoKey>> {
  const response = await fetcher(IAP_KEYS_URL, { cache: "no-store" });
  if (!response.ok) throw new Error(`IAP keys: ${response.status}`);
  const body = (await response.json()) as { keys?: (JsonWebKey & { kid?: string })[] };
  const keys = new Map<string, CryptoKey>();
  for (const jwk of body.keys ?? []) {
    if (!jwk.kid || jwk.kty !== "EC" || jwk.crv !== "P-256") continue;
    const { kid, ...material } = jwk;
    keys.set(kid, await crypto.subtle.importKey("jwk", material, { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"]));
  }
  return keys;
}

// Looks keys up by id from Google's published set, keeping a copy for an hour.
export function iapKeyLookup(fetcher: typeof fetch = fetch, now: () => number = Date.now): KeyLookup {
  let cached: KeySet | null = null;
  return async (kid) => {
    const fresh = cached && now() - cached.fetchedAt < KEYS_TTL_MS;
    if (!fresh || !cached?.keys.has(kid)) {
      try {
        cached = { keys: await fetchKeys(fetcher), fetchedAt: now() };
      } catch {
        if (!cached) return null;
      }
    }
    return cached?.keys.get(kid) ?? null;
  };
}
