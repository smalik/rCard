import "server-only";

export type Session = { subject: string };

// Passkey sign-in is the next M0 step. Until it lands, a development server
// can act as one person named by PLYTOS_DEV_USER; anywhere else nobody is
// signed in.
export async function currentSession(): Promise<Session | null> {
  const subject = process.env.PLYTOS_DEV_USER;
  if (process.env.PLYTOS_ENV === "dev" && subject) {
    return { subject };
  }
  return null;
}
