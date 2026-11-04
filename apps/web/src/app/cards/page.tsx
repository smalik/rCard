import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { ApiError, type CardSummary, listCards } from "../../lib/api";
import { KIND_LABELS } from "../../lib/cards";
import { currentSession } from "../../lib/session";

export const metadata: Metadata = { title: "Your cards" };
export const dynamic = "force-dynamic";

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

export default async function Cards({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const session = await currentSession();
  if (!session) redirect("/sign-in");
  const imported = Number((await searchParams).imported ?? "0");

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
        <div className="topbar-row">
          <h1>Your cards</h1>
          <Link className="link small" href="/import">
            Import a resume
          </Link>
        </div>
      </header>
      {Number.isInteger(imported) && imported > 0 && (
        <p className="panel notice" role="status">
          Saved {imported} {imported === 1 ? "card" : "cards"} from your resume.
        </p>
      )}
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
          <Link className="button primary file-button" href="/import">
            Import your resume
          </Link>
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
