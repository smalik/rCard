import Link from "next/link";

import { AppHeader } from "../../../components/hybrid";

export default function ImportNotFound() {
  return (
    <main className="page">
      <AppHeader back={{ href: "/import", label: "Back" }} />
      <div className="stack tight">
        <h1 className="title">This import isn&apos;t here any more.</h1>
        <p className="lede">
          It may have been deleted. Cards you approved from it are still in your cards.
        </p>
      </div>
      <div className="stack tight">
        <Link className="button primary" href="/cards">
          Go to your cards
        </Link>
        <Link className="text-button" href="/import">
          Bring in a resume
        </Link>
      </div>
    </main>
  );
}
