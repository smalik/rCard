import "server-only";

import { headers } from "next/headers";

import { IAP_ASSERTION_HEADER, iapKeyLookup, verifyIapAssertion } from "./iap";

export type Session = { subject: string };

const iapKeys = iapKeyLookup();

// Passkey sign-in is a later step. Until it lands:
// - On Cloud Run behind Google's Identity-Aware Proxy (PLYTOS_SIGN_IN=iap),
//   the person is the Google account the proxy let in, checked against the
//   proxy's signed assertion.
// - A development server can act as one person named by PLYTOS_DEV_USER.
// Anywhere else nobody is signed in.
export async function currentSession(): Promise<Session | null> {
  if (process.env.PLYTOS_SIGN_IN === "iap") {
    const assertion = (await headers()).get(IAP_ASSERTION_HEADER);
    const audience = process.env.PLYTOS_IAP_AUDIENCE ?? "";
    if (!assertion || !audience) return null;
    const who = await verifyIapAssertion(assertion, audience, iapKeys);
    return who ? { subject: `iap:${who.sub}` } : null;
  }
  const subject = process.env.PLYTOS_DEV_USER;
  if (process.env.PLYTOS_ENV === "dev" && subject) {
    return { subject };
  }
  return null;
}
