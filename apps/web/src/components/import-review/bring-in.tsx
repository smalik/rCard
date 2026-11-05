"use client";

// Bringing a resume in, and every file brought in so far: where each one is,
// with its side-by-side check and its audit a tap away. Nothing becomes a card
// until the person says so on the check.

import { ArrowLeft, ClipboardList, Ellipsis, FileText, Loader2, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ChangeEvent, type DragEvent, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import {
  ACCEPT_RESUME,
  FILENAME_HEADER,
  fileProblem,
  type ImportStatus,
  type ImportSummary,
  MAX_PASTE_CHARS,
  plural,
} from "@/lib/imports";
import { relativeTime } from "@/lib/library";
import { cn } from "@/lib/utils";

// Where a file is, in a few words, and what to do next.
export function fileState(file: ImportSummary): { text: string; next: string; waiting: boolean } {
  if (file.state === "reading") return { text: "Reading it now…", next: "Follow the reading", waiting: true };
  if (file.state === "failed") return { text: "Plytos couldn't read this one", next: "See what happened", waiting: false };
  const left = file.cards - file.approved - file.dropped;
  if (left > 0) {
    return {
      text: `${plural(left, "line")} ${left === 1 ? "waits" : "wait"} for you`,
      next: "Check it beside your file",
      waiting: true,
    };
  }
  return {
    text: file.approved > 0 ? `Kept ${plural(file.approved, "card")}` : "Nothing kept from it",
    next: "See it beside your file",
    waiting: false,
  };
}

function FileRow({ file, now, onDelete }: { file: ImportSummary; now: Date; onDelete: () => void }) {
  const href = `/import/${encodeURIComponent(file.id)}`;
  const state = fileState(file);
  return (
    <li className="flex items-center gap-3 rounded-card border bg-card p-4 shadow-card">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground">
        <FileText className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <Link href={href} className="block truncate text-[16px] font-semibold hover:underline">
          {file.file.name}
        </Link>
        <p className="text-[13.5px] text-muted-foreground">
          <span className={cn(state.waiting && "font-medium text-foreground")}>{state.text}</span>
          {" · "}
          {relativeTime(file.created_at, now)}
        </p>
      </div>
      <Button asChild size="sm" variant={state.waiting ? "default" : "outline"} className="hidden sm:inline-flex">
        <Link href={href}>{state.next}</Link>
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={`More for ${file.file.name}`}>
            <Ellipsis />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem asChild className="sm:hidden">
            <Link href={href}>{state.next}</Link>
          </DropdownMenuItem>
          {file.state === "read" && (
            <DropdownMenuItem asChild>
              <Link href={`${href}/audit`}>
                <ClipboardList /> See the audit
              </Link>
            </DropdownMenuItem>
          )}
          <DropdownMenuItem asChild>
            <a href={`${href}/original`} target="_blank" rel="noreferrer">
              <FileText /> Open your file
            </a>
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={onDelete}>
            <Trash2 /> Delete this file
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </li>
  );
}

export function BringIn({ files }: { files: ImportSummary[] }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [sending, setSending] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [pasting, setPasting] = useState(false);
  const [pasted, setPasted] = useState("");
  const [over, setOver] = useState(false);
  const [deleting, setDeleting] = useState<ImportSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const now = new Date();

  // The server keeps the file and answers at once; the reading goes on in the
  // background, and the file's own page follows it.
  async function send(data: Blob, name: string) {
    setProblem(null);
    setSending(name);
    try {
      const response = await fetch("/import/upload", {
        method: "POST",
        body: data,
        headers: { "Content-Type": "application/octet-stream", [FILENAME_HEADER]: encodeURIComponent(name) },
      });
      const body = (await response.json().catch(() => null)) as (ImportStatus & { error?: string }) | null;
      if (response.ok && body?.id) {
        router.push(`/import/${encodeURIComponent(body.id)}`);
        return;
      }
      setProblem(body?.error ?? "Plytos couldn't take that just now. Try again in a moment.");
    } catch {
      setProblem("The connection dropped. Check you're online and try again.");
    }
    setSending(null);
  }

  function take(file: File | undefined) {
    if (!file) return;
    const issue = fileProblem(file);
    if (issue) {
      setProblem(issue);
      return;
    }
    void send(file, file.name);
  }

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    take(file);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setOver(false);
    take(event.dataTransfer.files?.[0]);
  }

  async function remove(file: ImportSummary) {
    setBusy(true);
    const response = await fetch(`/import/${encodeURIComponent(file.id)}/delete`, { method: "POST" }).catch(
      () => null,
    );
    setBusy(false);
    setDeleting(null);
    if (!response?.ok) {
      setProblem("That didn't delete. Try again in a moment.");
      return;
    }
    router.refresh();
  }

  const tooLong = pasted.length > MAX_PASTE_CHARS;
  const sorted = [...files].sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <main className="mx-auto w-full max-w-3xl px-4 pt-6 sm:px-6 md:pt-10">
      <Link
        href="/resumes"
        className="-ml-1 inline-flex items-center gap-1 rounded-full px-1 text-[14px] font-medium text-primary"
      >
        <ArrowLeft className="size-4" /> Resumes
      </Link>
      <h1 className="mt-1 text-[32px] leading-none font-bold tracking-[-0.025em] md:text-[38px]">Bring in a resume</h1>
      <p className="mt-2 text-[15px] text-muted-foreground">
        Plytos rebuilds it, you check it line by line beside your own file, and nothing becomes a card until you
        say so. Your file stays private.
      </p>

      <section
        aria-label="Choose a file"
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={cn(
          "mt-6 rounded-card border border-dashed bg-card p-6 text-center shadow-card transition-colors",
          over && "border-primary bg-accent/60",
        )}
      >
        <input ref={input} type="file" accept={ACCEPT_RESUME} className="sr-only" onChange={onFile} tabIndex={-1} />
        {sending ? (
          <p className="flex items-center justify-center gap-2 text-[15px] font-medium" role="status">
            <Loader2 className="size-4 animate-spin" /> Sending {sending}…
          </p>
        ) : pasting ? (
          <form
            className="flex flex-col gap-3 text-left"
            onSubmit={(e) => {
              e.preventDefault();
              if (pasted.trim() && !tooLong) void send(new Blob([pasted], { type: "text/plain" }), "Pasted text.txt");
            }}
          >
            <label htmlFor="paste" className="text-[15px] font-medium">
              Paste your resume
            </label>
            <Textarea
              id="paste"
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              rows={10}
              autoFocus
              placeholder="Copy it from a document or your LinkedIn profile. Plain text is fine."
            />
            {tooLong && (
              <p className="text-[13px] text-destructive">
                That&apos;s longer than Plytos can read at once. Trim it under {MAX_PASTE_CHARS.toLocaleString()}{" "}
                characters.
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={!pasted.trim() || tooLong}>
                Read this
              </Button>
              <Button type="button" variant="ghost" onClick={() => setPasting(false)}>
                Never mind
              </Button>
            </div>
          </form>
        ) : (
          <>
            <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-accent text-primary">
              <Upload className="size-6" />
            </span>
            <p className="mt-3 text-[17px] font-semibold">Word or PDF works best</p>
            <p className="mt-1 text-[14px] text-muted-foreground">
              <span className="hidden md:inline">Drop it here, or choose it. </span>Up to 5 MB.
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              <Button onClick={() => input.current?.click()}>Choose a file</Button>
              <Button variant="ghost" onClick={() => setPasting(true)}>
                Paste the text instead
              </Button>
            </div>
          </>
        )}
        {problem && (
          <p role="alert" className="mt-3 text-[14px] text-destructive">
            {problem}
          </p>
        )}
      </section>

      {sorted.length > 0 && (
        <section aria-labelledby="your-files" className="mt-10">
          <h2 id="your-files" className="text-[20px] font-semibold tracking-[-0.015em]">
            Your files
          </h2>
          <p className="mt-1 text-[14px] text-muted-foreground">
            Each one keeps its check beside your file and its audit. Deleting a file keeps the cards you kept from it.
          </p>
          <ul className="mt-4 flex flex-col gap-3">
            {sorted.map((file) => (
              <FileRow key={file.id} file={file} now={now} onDelete={() => setDeleting(file)} />
            ))}
          </ul>
        </section>
      )}

      <Dialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {deleting?.file.name}?</DialogTitle>
            <DialogDescription>
              Plytos deletes the file and everything it read from it. The cards you kept stay yours.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(null)} disabled={busy}>
              Keep it
            </Button>
            <Button variant="destructive" onClick={() => deleting && void remove(deleting)} disabled={busy}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
