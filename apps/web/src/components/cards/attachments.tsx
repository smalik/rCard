"use client";

import { ExternalLink, FileText, FolderGit2, Link2, Paperclip, Plus, X } from "lucide-react";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  type Attachment,
  type AttachmentKind,
  attachmentKindFor,
  isWebAddress,
  MAX_ATTACHMENTS,
} from "@/lib/library";
import { cn } from "@/lib/utils";

const KINDS: Record<AttachmentKind, { label: string; icon: typeof FileText }> = {
  paper: { label: "Paper", icon: FileText },
  repo: { label: "Repository", icon: FolderGit2 },
  link: { label: "Link", icon: Link2 },
};

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Papers, repositories and links, as compact chips that open in a new tab. */
export function AttachmentChips({
  attachments,
  className,
}: {
  attachments: Attachment[];
  className?: string;
}) {
  if (attachments.length === 0) return null;
  return (
    <ul className={cn("flex flex-wrap gap-1.5", className)} aria-label="Attached">
      {attachments.map((a) => {
        const Icon = KINDS[a.kind].icon;
        return (
          <li key={a.url}>
            <a
              href={a.url}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex max-w-64 items-center gap-1.5 rounded-full border bg-card py-1 pr-2.5 pl-2 text-[12px] font-medium text-foreground/85 shadow-sheet transition-colors hover:border-primary/40 hover:text-foreground"
            >
              <Icon className="size-3.5 shrink-0 text-primary" strokeWidth={2.2} />
              <span className="truncate">{a.title}</span>
              <span className="sr-only">({KINDS[a.kind].label}, opens in a new tab)</span>
            </a>
          </li>
        );
      })}
    </ul>
  );
}

/** The back of a card: what's attached, with room to add and remove. */
export function AttachmentEditor({
  attachments,
  onChange,
}: {
  attachments: Attachment[];
  onChange: (next: Attachment[]) => void;
}) {
  const [adding, setAdding] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h4 className="flex items-center gap-1.5 text-[13px] font-semibold">
          <Paperclip className="size-3.5 text-muted-foreground" /> Evidence
        </h4>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => setAdding(true)}
          disabled={attachments.length >= MAX_ATTACHMENTS}
        >
          <Plus /> Attach
        </Button>
      </div>
      {attachments.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">
          Attach a paper you wrote, a repository, or a link that shows this work.
        </p>
      ) : (
        <ul className="flex flex-col divide-y rounded-xl border bg-card">
          {attachments.map((a) => {
            const Icon = KINDS[a.kind].icon;
            return (
              <li key={a.url} className="flex items-center gap-3 px-3 py-2.5">
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
                  <Icon className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] font-medium">{a.title}</p>
                  <p className="truncate text-[12px] text-muted-foreground">
                    {KINDS[a.kind].label} · {host(a.url)}
                    {a.note && ` · ${a.note}`}
                  </p>
                </div>
                <Button asChild size="icon-sm" variant="ghost">
                  <a href={a.url} target="_blank" rel="noopener noreferrer" aria-label={`Open ${a.title}`}>
                    <ExternalLink />
                  </a>
                </Button>
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`Remove ${a.title}`}
                  onClick={() => onChange(attachments.filter((x) => x.url !== a.url))}
                >
                  <X />
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <AddAttachment
        open={adding}
        onOpenChange={setAdding}
        taken={attachments.map((a) => a.url)}
        onAdd={(a) => {
          onChange([...attachments, a]);
          setAdding(false);
        }}
      />
    </div>
  );
}

function AddAttachment({
  open,
  onOpenChange,
  taken,
  onAdd,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  taken: string[];
  onAdd: (attachment: Attachment) => void;
}) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<AttachmentKind | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const guessed = isWebAddress(url) ? attachmentKindFor(url.trim()) : "link";
  const chosen = kind ?? guessed;

  function reset() {
    setUrl("");
    setTitle("");
    setKind(null);
    setNote("");
    setError(null);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    // The dialog is portaled out of the card's form in the page, but React
    // still bubbles its submit to that form, which would save the card.
    event.stopPropagation();
    const address = url.trim();
    if (!isWebAddress(address)) {
      setError("Paste a web address that starts with https://");
      return;
    }
    if (taken.includes(address)) {
      setError("That's already attached.");
      return;
    }
    onAdd({ kind: chosen, url: address, title: title.trim() || host(address), note: note.trim() });
    reset();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Attach evidence</DialogTitle>
          <DialogDescription>
            A paper you wrote, a repository, a talk, or press coverage. It saves with the card.
          </DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={submit}>
          <div className="grid gap-2">
            <Label htmlFor="attach-url">Web address</Label>
            <Input
              id="attach-url"
              inputMode="url"
              autoComplete="off"
              placeholder="https://"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              aria-invalid={error !== null}
            />
          </div>
          <div className="grid gap-2">
            <Label>What it is</Label>
            <div className="grid grid-cols-3 gap-1 rounded-xl bg-muted p-1" role="radiogroup">
              {(Object.keys(KINDS) as AttachmentKind[]).map((k) => {
                const Icon = KINDS[k].icon;
                return (
                  <button
                    key={k}
                    type="button"
                    role="radio"
                    aria-checked={chosen === k}
                    onClick={() => setKind(k)}
                    className={cn(
                      "flex h-9 items-center justify-center gap-1.5 rounded-lg text-[13px] font-medium text-muted-foreground transition-all",
                      chosen === k && "bg-card text-foreground shadow-sheet",
                    )}
                  >
                    <Icon className="size-3.5" />
                    {KINDS[k].label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="attach-title">Title</Label>
            <Input
              id="attach-title"
              maxLength={200}
              placeholder={isWebAddress(url) ? host(url.trim()) : "Shown on the card"}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="attach-note">Note (optional)</Label>
            <Input
              id="attach-note"
              maxLength={500}
              placeholder="Co-author, venue, or what to look at"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          {error && (
            <p role="alert" className="text-[13px] text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="submit">Attach</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
