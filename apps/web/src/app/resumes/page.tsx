import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { AppHeader, TabBar } from "../../components/hybrid";
import { ApiError, listResumes } from "../../lib/api";
import { type Resumes, resumeFor } from "../../lib/resumes";
import { currentSession } from "../../lib/session";
import { MakeResume } from "./make-resume";

import "./resumes.css";

export const metadata: Metadata = { title: "Resumes" };
export const dynamic = "force-dynamic";

export default async function ResumesPage() {
  const session = await currentSession();
  if (!session) redirect("/sign-in");

  let data: Resumes | null = null;
  try {
    data = await listResumes(session);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
  }

  return (
    <main className="screen">
      <AppHeader />
      <h1>Resumes</h1>
      {data === null && (
        <p className="panel attention" role="alert">
          Plytos couldn&apos;t load your resumes just now. Try again in a moment.
        </p>
      )}
      {data?.ready.map((file) => (
        <section className="panel resume-ready" key={file.id}>
          <h2>Your resume is ready to set up</h2>
          <p className="muted small">
            From {file.file.name}: the {file.approved} {file.approved === 1 ? "card" : "cards"} you
            kept, in your own words and the file&apos;s order.
          </p>
          <MakeResume importId={file.id} />
        </section>
      ))}
      {data && data.resumes.length === 0 && data.ready.length === 0 && (
        <section className="panel">
          <h2>No resumes yet</h2>
          <p className="muted">
            Share your resume in Talk and keep its cards. Plytos sets it up as you wrote it, then
            makes versions of it for the roles you go after.
          </p>
          <Link className="button primary" href="/talk">
            Go to Talk
          </Link>
        </section>
      )}
      {data && data.resumes.length > 0 && (
        <ul className="card-list">
          {data.resumes.map((resume) => (
            <li key={resume.id}>
              <Link className="resume-row" href={`/resumes/${encodeURIComponent(resume.id)}`}>
                <span className="resume-row-name">{resume.name}</span>
                <span className="muted small">{resumeFor(resume)}</span>
                <span className="resume-row-meta">Version {resume.head_number}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <TabBar current="/resumes" />
    </main>
  );
}
