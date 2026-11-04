import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sign in" };

export default function SignIn() {
  return (
    <main className="screen center">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true" />
        <h1>Plytos</h1>
        <p className="tagline">Play to your strengths.</p>
      </div>
      <section className="panel">
        <button className="button primary" type="button" disabled>
          Sign in with a passkey
        </button>
        <p className="muted small">
          Sign-in isn&apos;t open yet. Your cards stay private: nothing in Plytos is public or
          searchable unless you choose to share it.
        </p>
      </section>
    </main>
  );
}
