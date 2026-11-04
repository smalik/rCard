// A resume as it reads: the header, each employment with its titles latest
// first and the lines switched on under them, then education, skills and the
// rest. With `edit`, each line and employment gets the controls to leave it
// out or bring it back. Holds no state, so it renders on the server or inside
// a client screen alike.

import {
  faArrowDown,
  faArrowUp,
  faPlus,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { lineParts, type RenderedItem, type RenderedResume } from "../lib/resumes";
import { Icon } from "./icon";

export type ResumeEdits = {
  switchOff: (item: string) => void;
  switchOn: (entry: string, item: string) => void;
  leaveOut: (entry: string) => void;
  bringBack: (entry: string) => void;
  setFold: (entry: string, fold: boolean) => void;
  move: (entry: string, by: -1 | 1) => void;
  busy: boolean;
};

function Line({ item, edit }: { item: RenderedItem; edit?: ResumeEdits }) {
  const { text, detail } = lineParts(item);
  return (
    <li className="doc-line" data-wording={item.wording}>
      <span className="doc-line-text">
        {text}
        {item.wording === "target" && (
          <span className="visually-hidden"> (worded for this version)</span>
        )}
      </span>
      {edit && (
        <button
          className="doc-x"
          type="button"
          disabled={edit.busy}
          aria-label={`Leave out: ${item.text}`}
          onClick={() => edit.switchOff(item.card)}
        >
          <Icon icon={faXmark} size={11} />
        </button>
      )}
      {detail && <span className="doc-line-detail">{detail}</span>}
    </li>
  );
}

export function ResumeDocument({
  page,
  edit,
  compact = false,
}: {
  page: RenderedResume;
  edit?: ResumeEdits;
  compact?: boolean;
}) {
  const { header } = page;
  const contact = [header.location, header.email, header.phone, ...header.links].filter(Boolean);
  return (
    <article className={compact ? "doc doc-compact" : "doc"} aria-label="Resume">
      {(header.name || contact.length > 0) && (
        <header className="doc-head">
          {header.name && <h2 className="doc-name">{header.name}</h2>}
          {header.headline && <p className="doc-headline">{header.headline}</p>}
          {contact.length > 0 && <p className="doc-contact">{contact.join(" · ")}</p>}
          {header.summary && <p className="doc-summary">{header.summary}</p>}
        </header>
      )}

      {page.entries.length > 0 && <h3 className="doc-section">Experience</h3>}
      {page.entries.map((entry, i) => {
        const titled = entry.roles.filter((r) => r.card !== null);
        const canFold = titled.length > 1 || entry.earlier_titles.length > 0;
        return (
          <section className="doc-entry" key={entry.card}>
            <div className="doc-employer">
              <p>
                <b>{entry.employer}</b>
                {entry.location && <span>, {entry.location}</span>}
              </p>
              {entry.dates && <p className="doc-dates">{entry.dates}</p>}
            </div>
            {edit && (
              <div className="doc-tools">
                <button
                  type="button"
                  disabled={edit.busy || i === 0}
                  aria-label={`Move ${entry.employer} up`}
                  onClick={() => edit.move(entry.card, -1)}
                >
                  <Icon icon={faArrowUp} size={11} />
                </button>
                <button
                  type="button"
                  disabled={edit.busy || i === page.entries.length - 1}
                  aria-label={`Move ${entry.employer} down`}
                  onClick={() => edit.move(entry.card, 1)}
                >
                  <Icon icon={faArrowDown} size={11} />
                </button>
                {canFold && (
                  <button
                    type="button"
                    disabled={edit.busy}
                    onClick={() => edit.setFold(entry.card, !entry.fold_earlier)}
                  >
                    {entry.fold_earlier ? "Show each title" : "Fold earlier titles"}
                  </button>
                )}
                <button
                  type="button"
                  disabled={edit.busy}
                  onClick={() => edit.leaveOut(entry.card)}
                >
                  Leave out
                </button>
              </div>
            )}
            {entry.roles.map((role) => (
              <div className="doc-role" key={role.card ?? "employment"}>
                {role.card !== null && (
                  <p className="doc-title">
                    <span>{role.title}</span>
                    {role.dates && <span className="doc-dates">{role.dates}</span>}
                  </p>
                )}
                {role.items.length > 0 && (
                  <ul className="doc-lines">
                    {role.items.map((item) => (
                      <Line key={item.card} item={item} edit={edit} />
                    ))}
                  </ul>
                )}
              </div>
            ))}
            {entry.earlier_titles.length > 0 && (
              <p className="doc-earlier">Earlier: {entry.earlier_titles.join("; ")}</p>
            )}
            {edit && entry.hidden.length > 0 && (
              <details className="doc-hidden">
                <summary>
                  {entry.hidden.length} more {entry.hidden.length === 1 ? "line" : "lines"} on
                  file
                </summary>
                <ul>
                  {entry.hidden.map((item) => (
                    <li key={item.card}>
                      <span>{item.text}</span>
                      <button
                        type="button"
                        disabled={edit.busy}
                        aria-label={`Switch on: ${item.text}`}
                        onClick={() => edit.switchOn(entry.card, item.card)}
                      >
                        <Icon icon={faPlus} size={11} />
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
        );
      })}

      {page.sections.map((section) => (
        <section className="doc-entry" key={section.kind}>
          <h3 className="doc-section">{section.label}</h3>
          <ul className="doc-lines plain">
            {section.items.map((item) => (
              <Line key={item.card} item={item} edit={edit} />
            ))}
          </ul>
        </section>
      ))}

      {edit && page.left_out.length > 0 && (
        <section className="doc-left-out">
          <h3 className="doc-section">Left out</h3>
          <ul>
            {page.left_out.map((e) => (
              <li key={e.card}>
                <span>
                  {e.employer}
                  {e.dates && <em> · {e.dates}</em>}
                </span>
                <button
                  type="button"
                  disabled={edit.busy}
                  onClick={() => edit.bringBack(e.card)}
                >
                  <Icon icon={faPlus} size={11} /> Add
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {page.missing > 0 && (
        <p className="doc-missing">
          {page.missing} {page.missing === 1 ? "line is" : "lines are"} hidden because the card
          was archived.
        </p>
      )}
    </article>
  );
}
