import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ApiError, type CardKind, type CardSummary, listCards } from "../../lib/api";
import { currentSession } from "../../lib/session";

export const metadata: Metadata = { title: "Your cards" };
export const dynamic = "force-dynamic";

const KIND_LABELS: Record<CardKind, string> = {
  role: "Role",
  accomplishment: "Accomplishment",
  skill: "Skill",
  project: "Project",
  education: "Education",
  credential: "Credential",
  story: "Story",
};

function CardRow({ card }: { card: CardSummary }) {
  return (
    <li className="card">
      <div className="card-top">
        <span className="chip">{KIND_LABELS[card.kind]}</span>
        <span className="muted small">v{card.main_version}</span>
      </div>
      <p className="card-headline">{card.headline ?? "Redacted"}</p>
      {card.variants > 0 && (
        <p className="muted small">
          {card.variants} {card.variants === 1 ? "variant" : "variants"}
          {card.variants_behind > 0 && (
            <span className="attention">
              {" "}
              · {card.variants_behind} {card.variants_behind === 1 ? "needs" : "need"} a refresh
            </span>
          )}
        </p>
      )}
    </li>
  );
}

export default async function Cards() {
  const session = await currentSession();
  if (!session) redirect("/sign-in");

  let cards: CardSummary[] | null = null;
  let failed = false;
  try {
    cards = await listCards(session);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }

  return (
    <main className="screen">
      <header className="topbar">
        <h1>Your cards</h1>
      </header>
      {failed && (
        <p className="panel attention" role="alert">
          Plytos couldn&apos;t load your cards just now. Try again in a moment.
        </p>
      )}
      {cards && cards.length === 0 && (
        <section className="panel">
          <h2>No cards yet</h2>
          <p className="muted">
            Cards are the building blocks of every resume you send: one role, one accomplishment,
            one skill at a time. Importing your current resume will start your first ones.
          </p>
        </section>
      )}
      {cards && cards.length > 0 && (
        <ul className="card-list">
          {cards.map((card) => (
            <CardRow key={card.id} card={card} />
          ))}
        </ul>
      )}
    </main>
  );
}
