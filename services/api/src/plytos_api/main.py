"""HTTP API. Only the web app's server calls it; it is never public."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from urllib.parse import quote, unquote
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from plytos_api.agents.check_in import plan_confirmation, plan_label
from plytos_api.agents.crew import crew
from plytos_api.agents.model import (
    MAX_MESSAGE,
    CheckInPlan,
    CheckIns,
    MessageView,
    ProposalState,
    ProposalView,
    RunView,
    TidbitView,
)
from plytos_api.agents.runtime import BackgroundWorker, Worker
from plytos_api.agents.store import (
    AgentRecordNotFoundError,
    AgentStore,
    CheckInPlanError,
    ProposalConflictError,
)
from plytos_api.agents.summarizer import (
    SummaryUnavailableError,
    needs_first_summary,
    summarize,
)
from plytos_api.agents.thinking import Usage, thinker_for
from plytos_api.auth import resolve_user
from plytos_api.cards.model import CardKind, MainContent, TargetKind, VariantContent
from plytos_api.cards.repository import (
    Author,
    CardDetail,
    CardNotFoundError,
    CardOrderError,
    CardRepository,
    CardSummary,
    LibraryCard,
    ParentError,
    SaveResult,
    StaleHeadError,
    TargetView,
    UnsupportedClaimsError,
    VariantExistsError,
    VersionView,
)
from plytos_api.config import Settings, get_settings
from plytos_api.db import Database
from plytos_api.imports.ai import reader_for
from plytos_api.imports.extract import MAX_BYTES, UnsupportedFileError, detect_format
from plytos_api.imports.matching import CardMatch
from plytos_api.imports.pictures import page_picture
from plytos_api.imports.store import (
    ImportConflictError,
    ImportNotFoundError,
    ImportProgress,
    ImportStatus,
    ImportStore,
    ImportSummary,
    ImportView,
    KeepCard,
    MatchChoice,
    find_matches,
)
from plytos_api.imports.worker import ImportWorker
from plytos_api.keys import KeyShreddedError, Vault, kek_from_setting
from plytos_api.resumes.as_written import as_written
from plytos_api.resumes.model import ResumeChange, ResumeContent, ResumeHeader, keep_wording
from plytos_api.resumes.render import RenderedHighlights, RenderedResume, describe, render
from plytos_api.resumes.store import (
    DeletionPlan,
    ResumeDetail,
    ResumeNotFoundError,
    ResumeStore,
    ResumeSummary,
    ResumeVersionView,
    StaleResumeError,
)

FILENAME_HEADER = "x-plytos-filename"
ORIGINAL_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "text": "text/plain; charset=utf-8",
}

# Sent on every response: nothing Plytos serves may be indexed or cached.
SECURITY_HEADERS = {
    "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet, noimageindex",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


class CreateCard(BaseModel):
    kind: CardKind
    content: MainContent


class Reorder(BaseModel):
    # The card they sit under, or None for the top of the tree.
    parent_id: UUID | None = None
    card_ids: list[UUID] = Field(min_length=1, max_length=500)


class SaveMainVersion(BaseModel):
    base_version_id: UUID
    content: MainContent


class Rewrite(BaseModel):
    # Also rewrite the parts in the person's own words. Their words stay in
    # the card's history either way.
    replace_own: bool = False


class Rewritten(BaseModel):
    headline: bool
    stories: int
    # Parts left as they were because they cited a number no card has.
    dropped: int


class CreateTarget(BaseModel):
    kind: TargetKind
    name: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None = None


class CreateVariant(BaseModel):
    target_id: UUID
    content: VariantContent


class SaveVariantVersion(BaseModel):
    base_version_id: UUID
    content: VariantContent


CardRef = Annotated[str, Path(pattern=r"^card-[0-9]{1,4}$")]
PageNumber = Annotated[int, Path(ge=1, le=999)]


class Settle(BaseModel):
    finding: int = Field(ge=0)
    answer: Literal["chosen", "as_is", "on_card", "later"]
    value: str | None = Field(default=None, max_length=40)


class Decide(BaseModel):
    state: Literal["later", "dropped", "pending"]


class Place(BaseModel):
    # The proposed card it sits under, or None for the top of the tree.
    parent_ref: str | None = Field(default=None, pattern=r"^card-[0-9]{1,4}$")


class Fix(BaseModel):
    # The card's words and dates as the person corrected them, or None to take
    # the correction back.
    content: MainContent | None = None


class Approve(BaseModel):
    content: MainContent | None = None
    # For a card that matches one of the person's: "update" saves it as that
    # card's next version (the default), "keep" links it to theirs as it is,
    # "separate" makes a new card.
    choice: MatchChoice | None = None


class Approved(BaseModel):
    card: CardDetail
    progress: ImportProgress


class KeepGroup(BaseModel):
    # Approved in one go, each under the card it sits under.
    keep: list[KeepCard] = Field(default_factory=list, max_length=500)
    leave_out: list[Annotated[str, Field(pattern=r"^card-[0-9]{1,4}$")]] = Field(
        default_factory=list, max_length=500
    )
    later: list[Annotated[str, Field(pattern=r"^card-[0-9]{1,4}$")]] = Field(
        default_factory=list, max_length=500
    )


class Verification(BaseModel):
    ok: bool
    problems: list[str]


class Say(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE)


class Keep(BaseModel):
    # The person's edits to the proposed card, if they changed it before keeping it.
    content: MainContent | None = None


class Shared(BaseModel):
    messages: list[MessageView]
    resume: ImportSummary


class Kept(BaseModel):
    proposal: ProposalView
    card: CardDetail


class MakeAsWritten(BaseModel):
    import_id: UUID


class SaveResume(BaseModel):
    base_version_id: UUID
    content: ResumeContent


class RestoreResume(BaseModel):
    number: int = Field(ge=1)
    base_version_id: UUID


class NameVersion(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class DeleteVersions(BaseModel):
    base_version_id: UUID
    # Every version after it goes too.
    after: bool = False
    # Resumes made from it to delete with it; the rest stay and re-center.
    with_branches: list[UUID] = Field(default_factory=list, max_length=100)


class RenameResume(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TakeChanges(BaseModel):
    # The changes to take, by key. None of them passes on every change.
    keys: list[str] = Field(max_length=1000)
    base_version_id: UUID
    # The parent's version the person reviewed, from parent-changes.
    parent_version_id: UUID | None = None


class AskForVersion(BaseModel):
    # What the person asked, such as "Make a version for product roles at fintech companies".
    text: str = Field(min_length=1, max_length=MAX_MESSAGE)


class CopyResume(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # Who the copy is for, in the person's words.
    target: str = Field(min_length=1, max_length=200)
    target_kind: TargetKind = "custom"


class KeepResume(BaseModel):
    # The person's changes to the proposed resume, if they made any first.
    content: ResumeContent | None = None
    # The cards whose proposed wording the person kept; None keeps them all.
    rewordings: list[UUID] | None = None


class Resumes(BaseModel):
    resumes: list[ResumeSummary]
    # Files with kept cards that no resume was made from yet.
    ready: list[ImportSummary]


class LatestContact(BaseModel):
    """The top of the resume changed most recently, for the contact and
    highlights cards on Cards."""

    resume_id: UUID
    resume_name: str
    base_version_id: UUID
    header: ResumeHeader
    highlights: RenderedHighlights | None


class ResumePage(BaseModel):
    resume: ResumeDetail
    page: RenderedResume


class ResumeVersionPage(BaseModel):
    version: ResumeVersionView
    content: ResumeContent
    page: RenderedResume


class Deleted(BaseModel):
    # The resume as it is now; None when deleting took its last version.
    resume: ResumePage | None


class LabeledChange(BaseModel):
    change: ResumeChange
    label: str


class ParentChanges(BaseModel):
    # The parent's version these changes run to; send it back when taking them.
    parent_version_id: UUID | None
    changes: list[LabeledChange]


class ProposedResume(BaseModel):
    proposal: ProposalView
    parent_name: str | None
    page: RenderedResume


class KeptResume(BaseModel):
    proposal: ProposalView
    resume: ResumeDetail


class CheckInsSet(BaseModel):
    check_ins: CheckIns
    # What Plytos says about the change, in the conversation.
    message: MessageView


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.database_url, min_size=settings.database_pool_min)
    vault = Vault(kek_from_setting(settings.kek, allow_local=settings.dev_shortcuts))
    reader = reader_for(
        settings.ai_provider,
        settings.ai_model,
        settings.ai_effort,
        settings.ai_vertex_project,
        settings.ai_vertex_region,
    )
    # For the one agent the person can ask to write straight away (the
    # Summarizer, from a card). Every other agent runs from the queue.
    thinker = thinker_for(
        settings.ai_provider,
        settings.ai_model,
        settings.ai_effort,
        settings.ai_vertex_project,
        settings.ai_vertex_region,
    )

    # The API reads uploads itself unless told a separate worker does. The agents
    # run inside it in development and while one person uses the cloud setup;
    # once more do, they run as their own service (python -m plytos_api.agents),
    # which reads uploads too.
    background: list[BackgroundWorker] = []
    if settings.agents_inline:
        background.append(BackgroundWorker(Worker(db, vault, crew(settings)), name="agents"))
    if settings.imports_inline or settings.agents_inline:
        background.append(
            BackgroundWorker(ImportWorker(db, vault, reader), every_seconds=1.0, name="imports")
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.open()
        for worker in background:
            worker.start()
        try:
            yield
        finally:
            for worker in background:
                worker.stop()
            db.close()

    docs = settings.dev_shortcuts
    app = FastAPI(
        title="Plytos API",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.vault = vault

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    @app.exception_handler(CardNotFoundError)
    async def not_found(_: Request, __: CardNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": "Not found"}, status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(CardOrderError)
    async def card_order(_: Request, exc: CardOrderError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_409_CONFLICT)

    @app.exception_handler(StaleHeadError)
    async def stale(_: Request, exc: StaleHeadError) -> JSONResponse:
        return JSONResponse(
            {
                "detail": "This card changed since your edit started. Review the latest version.",
                "current_head_id": str(exc.current_head_id) if exc.current_head_id else None,
            },
            status_code=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(UnsupportedClaimsError)
    async def unsupported(_: Request, exc: UnsupportedClaimsError) -> JSONResponse:
        return JSONResponse(
            {"detail": "A variant can't add or change facts.", "problems": exc.problems},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @app.exception_handler(ParentError)
    async def bad_parent(_: Request, exc: ParentError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)

    @app.exception_handler(VariantExistsError)
    async def variant_exists(_: Request, __: VariantExistsError) -> JSONResponse:
        return JSONResponse(
            {"detail": "This card already has a variant for that target."},
            status_code=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(UnsupportedFileError)
    async def unsupported_file(_: Request, exc: UnsupportedFileError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)

    @app.exception_handler(ImportNotFoundError)
    async def import_not_found(_: Request, __: ImportNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": "Not found"}, status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(ImportConflictError)
    async def import_conflict(_: Request, exc: ImportConflictError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_409_CONFLICT)

    @app.exception_handler(AgentRecordNotFoundError)
    async def agent_record_not_found(_: Request, __: AgentRecordNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": "Not found"}, status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(ProposalConflictError)
    async def proposal_conflict(_: Request, exc: ProposalConflictError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_409_CONFLICT)

    @app.exception_handler(ResumeNotFoundError)
    async def resume_not_found(_: Request, __: ResumeNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": "Not found"}, status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(StaleResumeError)
    async def stale_resume(_: Request, exc: StaleResumeError) -> JSONResponse:
        return JSONResponse(
            {
                "detail": "This resume changed since you opened it. Review the latest version.",
                "current_head_id": str(exc.current_head_id) if exc.current_head_id else None,
            },
            status_code=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(KeyShreddedError)
    async def shredded(_: Request, __: KeyShreddedError) -> JSONResponse:
        return JSONResponse({"detail": "Gone"}, status_code=status.HTTP_410_GONE)

    User = Annotated[UUID, Depends(resolve_user)]

    def repo(conn: psycopg.Connection, user_id: UUID) -> CardRepository:
        cipher = vault.cipher_for(conn, user_id)

        def sum_up(employment_id: UUID) -> None:
            # A burst of edits to one job is summed up once, a little after.
            AgentStore(conn, user_id, cipher).enqueue(
                "summarizer",
                "card",
                employment_id,
                dedupe_key=f"summarize-{employment_id}",
                delay_seconds=settings.summary_delay_seconds,
            )

        hook = sum_up if thinker is not None else None
        return CardRepository(conn, user_id, cipher, on_job_changed=hook)

    def person(user_id: UUID) -> Author:
        return Author("person", str(user_id))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/me")
    def me(user_id: User) -> dict[str, UUID]:
        return {"id": user_id}

    @app.get("/v1/cards")
    def list_cards(user_id: User) -> list[CardSummary]:
        with db.as_user(user_id) as conn:
            return repo(conn, user_id).list_cards()

    @app.get("/v1/library")
    def library(user_id: User) -> list[LibraryCard]:
        """Every card, with the jobs Plytos is about to sum up, or summing up
        now, marked `writing`. A job with accomplishments and nothing summed up
        yet is queued the first time it's seen."""
        with db.as_user(user_id) as conn:
            cards = repo(conn, user_id).library()
            if thinker is None:
                return cards
            store = agents(conn, user_id)
            asked = store.runs_about("summarizer", waiting=False)
            for employment_id in needs_first_summary(cards):
                if employment_id not in asked:
                    store.enqueue(
                        "summarizer",
                        "card",
                        employment_id,
                        dedupe_key=f"summarize-{employment_id}",
                    )
            # Jobs Plytos is writing for now or in a moment. A run no worker has
            # picked up two minutes after it was due doesn't count.
            writing = store.runs_in_hand("summarizer", within_seconds=120)
            for card in cards:
                card.writing = card.id in writing
            return cards

    @app.post("/v1/cards/reorder", status_code=status.HTTP_204_NO_CONTENT)
    def reorder(body: Reorder, user_id: User) -> None:
        with db.as_user(user_id) as conn:
            repo(conn, user_id).reorder(body.parent_id, body.card_ids, person(user_id))

    @app.post("/v1/cards", status_code=status.HTTP_201_CREATED)
    def create_card(body: CreateCard, user_id: User) -> CardDetail:
        with db.as_user(user_id) as conn:
            return repo(conn, user_id).create_card(body.kind, body.content, person(user_id))

    @app.get("/v1/cards/{card_id}")
    def get_card(card_id: UUID, user_id: User) -> CardDetail:
        with db.as_user(user_id) as conn:
            return repo(conn, user_id).card_detail(card_id)

    @app.post("/v1/cards/{card_id}/versions", status_code=status.HTTP_201_CREATED)
    def save_main(card_id: UUID, body: SaveMainVersion, user_id: User) -> SaveResult:
        with db.as_user(user_id) as conn:
            return repo(conn, user_id).save_main_version(
                card_id, body.base_version_id, body.content, person(user_id)
            )

    @app.post("/v1/cards/{card_id}/summaries")
    def rewrite_summaries(card_id: UUID, body: Rewrite, user_id: User) -> Rewritten:
        """Writes an employment's headline and its titles' stories again now,
        from the accomplishments under them. The person's own words are kept
        unless `replace_own`; theirs stay in the history either way."""
        if thinker is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Plytos can't write while AI is off."
            )
        with db.as_user(user_id) as conn:
            cards = repo(conn, user_id)
            if cards.card_detail(card_id).kind != "employment":
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "Only a job has a headline to write."
                )
            usage = Usage()
            try:
                written = summarize(
                    cards, thinker, card_id, usage, force=True, replace_own=body.replace_own
                )
            except SummaryUnavailableError as exc:
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY, "Plytos couldn't write that just now. Try again."
                ) from exc
            finally:
                if usage.model is not None:
                    agents(conn, user_id).record_run("summarizer", "card", card_id, usage)
        return Rewritten(
            headline=written.headline, stories=written.stories, dropped=written.dropped
        )

    @app.get("/v1/cards/{card_id}/versions")
    def main_history(card_id: UUID, user_id: User) -> list[VersionView]:
        with db.as_user(user_id) as conn:
            return repo(conn, user_id).history(card_id, None)

    @app.post("/v1/cards/{card_id}/variants", status_code=status.HTTP_201_CREATED)
    def create_variant(card_id: UUID, body: CreateVariant, user_id: User) -> CardDetail:
        with db.as_user(user_id) as conn:
            return repo(conn, user_id).create_variant(
                card_id, body.target_id, body.content, person(user_id)
            )

    @app.post(
        "/v1/cards/{card_id}/variants/{target_id}/versions", status_code=status.HTTP_201_CREATED
    )
    def save_variant(
        card_id: UUID, target_id: UUID, body: SaveVariantVersion, user_id: User
    ) -> SaveResult:
        with db.as_user(user_id) as conn:
            return repo(conn, user_id).save_variant_version(
                card_id, target_id, body.base_version_id, body.content, person(user_id)
            )

    @app.get("/v1/cards/{card_id}/variants/{target_id}/versions")
    def variant_history(card_id: UUID, target_id: UUID, user_id: User) -> list[VersionView]:
        with db.as_user(user_id) as conn:
            return repo(conn, user_id).history(card_id, target_id)

    @app.get("/v1/cards/{card_id}/verify")
    def verify(card_id: UUID, user_id: User) -> Verification:
        with db.as_user(user_id) as conn:
            problems = repo(conn, user_id).verify(card_id)
        return Verification(ok=not problems, problems=problems)

    @app.get("/v1/targets")
    def list_targets(user_id: User) -> list[TargetView]:
        with db.as_user(user_id) as conn:
            return repo(conn, user_id).list_targets()

    @app.post("/v1/targets", status_code=status.HTTP_201_CREATED)
    def create_target(body: CreateTarget, user_id: User) -> TargetView:
        with db.as_user(user_id) as conn:
            return repo(conn, user_id).create_target(body.kind, body.name, body.parent_id)

    async def read_upload(request: Request) -> tuple[bytes, str]:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE, "Resumes over 5 MB aren't supported."
            )
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > MAX_BYTES:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE, "Resumes over 5 MB aren't supported."
                )
        if not data:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty.")
        filename = unquote(request.headers.get(FILENAME_HEADER, "") or "resume")[:200]
        return bytes(data), filename

    def imports(conn: psycopg.Connection, user_id: UUID) -> ImportStore:
        return ImportStore(conn, user_id, vault.cipher_for(conn, user_id))

    @app.post("/v1/imports", status_code=status.HTTP_202_ACCEPTED)
    async def create_import(request: Request, user_id: User) -> ImportStatus:
        """Keeps a resume, encrypted, to be read in the background, and says where
        the reading is. The proposed cards and the audit come with the import once
        it's read. No card is saved until the person approves it.

        The body is the file itself. The file name comes in a header, not the
        URL, because URLs land in request logs and resume file names carry names.
        A file that isn't Word, PDF or text is turned away here, before it's kept.
        """
        data, filename = await read_upload(request)
        fmt = detect_format(data, filename)

        def keep() -> ImportStatus:
            with db.as_user(user_id) as conn:
                return imports(conn, user_id).keep(data, filename, fmt)

        return await run_in_threadpool(keep)

    @app.get("/v1/imports")
    def list_imports(user_id: User) -> list[ImportSummary]:
        with db.as_user(user_id) as conn:
            return imports(conn, user_id).summaries()

    @app.get("/v1/imports/{import_id}")
    def get_import(import_id: UUID, user_id: User) -> ImportView:
        with db.as_user(user_id) as conn:
            view = imports(conn, user_id).get(import_id)
            if view.result is not None:
                cards = repo(conn, user_id).main_contents()
                view.matches = find_matches(view.result, view.progress, cards)
            return view

    @app.get("/v1/imports/{import_id}/matches")
    def import_matches(import_id: UUID, user_id: User) -> dict[str, CardMatch]:
        """The person's cards that the import's proposed cards stand for, by ref,
        as their decisions stand. Asked again after each decision."""
        with db.as_user(user_id) as conn:
            return imports(conn, user_id).matches(import_id, repo(conn, user_id))

    @app.get("/v1/imports/{import_id}/status")
    def import_status(import_id: UUID, user_id: User) -> ImportStatus:
        """Where the reading is, cheap enough to ask every second or two."""
        with db.as_user(user_id) as conn:
            return imports(conn, user_id).status(import_id)

    @app.post("/v1/imports/{import_id}/read-again")
    def read_again(import_id: UUID, user_id: User) -> ImportStatus:
        """Tries a reading that failed once more."""
        with db.as_user(user_id) as conn:
            return imports(conn, user_id).read_again(import_id)

    @app.get("/v1/imports/{import_id}/original")
    def get_original(import_id: UUID, user_id: User) -> Response:
        """The person's original file, exactly as they gave it."""
        with db.as_user(user_id) as conn:
            info, data = imports(conn, user_id).original(import_id)
        return Response(
            content=data,
            media_type=ORIGINAL_TYPES[info.format],
            headers={FILENAME_HEADER: quote(info.name)},
        )

    @app.get("/v1/imports/{import_id}/pages/{page}")
    def get_page(import_id: UUID, page: PageNumber, user_id: User) -> Response:
        """A page of the person's PDF as a picture, to check what was read from a scan
        against. Drawn from the kept file each time; nothing is stored."""
        with db.as_user(user_id) as conn:
            info, data = imports(conn, user_id).original(import_id)
        picture = page_picture(data, page) if info.format == "pdf" else None
        if picture is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "That page isn't in this file.")
        return Response(
            content=picture, media_type="image/jpeg", headers={"Cache-Control": "no-store"}
        )

    @app.delete("/v1/imports/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_import(import_id: UUID, user_id: User) -> None:
        """Deletes the original file and everything read from it. Approved cards stay."""
        with db.as_user(user_id) as conn:
            imports(conn, user_id).delete(import_id)

    @app.post("/v1/imports/{import_id}/settle")
    def settle(import_id: UUID, body: Settle, user_id: User) -> ImportProgress:
        with db.as_user(user_id) as conn:
            return imports(conn, user_id).settle(import_id, body.finding, body.answer, body.value)

    @app.post("/v1/imports/{import_id}/cards/{ref}/decision")
    def decide(import_id: UUID, ref: CardRef, body: Decide, user_id: User) -> ImportProgress:
        with db.as_user(user_id) as conn:
            return imports(conn, user_id).decide(import_id, ref, body.state)

    @app.post("/v1/imports/{import_id}/cards/{ref}/place")
    def place(import_id: UUID, ref: CardRef, body: Place, user_id: User) -> ImportProgress:
        """Answers where a card belongs: which job a result is from, or which
        employer a title was at."""
        with db.as_user(user_id) as conn:
            return imports(conn, user_id).place(import_id, ref, body.parent_ref)

    @app.post("/v1/imports/{import_id}/cards/{ref}/fix")
    def fix(import_id: UUID, ref: CardRef, body: Fix, user_id: User) -> ImportProgress:
        """Records the person's correction to a proposed card before it's approved,
        or takes it back."""
        with db.as_user(user_id) as conn:
            return imports(conn, user_id).fix(import_id, ref, body.content)

    @app.post("/v1/imports/{import_id}/cards/{ref}/approve", status_code=status.HTTP_201_CREATED)
    def approve(import_id: UUID, ref: CardRef, body: Approve, user_id: User) -> Approved:
        """Saves one proposed card as an approved card. AI never calls this: the
        wording is the person's own, from their resume or as they edited it."""
        with db.as_user(user_id) as conn:
            card, progress = imports(conn, user_id).approve(
                import_id, ref, body.content, repo(conn, user_id), person(user_id), body.choice
            )
        return Approved(card=card, progress=progress)

    @app.post("/v1/imports/{import_id}/keep")
    def keep_cards(import_id: UUID, body: KeepGroup, user_id: User) -> ImportView:
        """Decides a group of proposed cards at once, as the person goes through
        a job in the conversation: keeps some, leaves some out, sets some aside.
        All or nothing. Answers with the import as it now stands, matches too."""
        with db.as_user(user_id) as conn:
            store = imports(conn, user_id)
            cards = repo(conn, user_id)
            store.keep_group(
                import_id, body.keep, cards, person(user_id), body.leave_out, body.later
            )
            view = store.get(import_id)
            if view.result is not None:
                view.matches = find_matches(view.result, view.progress, cards.main_contents())
            return view

    def agents(conn: psycopg.Connection, user_id: UUID) -> AgentStore:
        return AgentStore(conn, user_id, vault.cipher_for(conn, user_id))

    @app.get("/v1/conversation")
    def conversation(
        user_id: User, before: UUID | None = None, limit: int = Query(50, ge=1, le=200)
    ) -> list[MessageView]:
        """The latest messages, oldest first. Pass the oldest id as `before` to page back."""
        with db.as_user(user_id) as conn:
            return agents(conn, user_id).conversation(limit, before)

    @app.post("/v1/conversation", status_code=status.HTTP_201_CREATED)
    def say(body: Say, user_id: User) -> MessageView:
        """Saves the person's message. The Listener reads it and answers shortly after."""
        with db.as_user(user_id) as conn:
            return agents(conn, user_id).say(body.text)

    @app.post("/v1/conversation/resume", status_code=status.HTTP_201_CREATED)
    async def share_resume(request: Request, user_id: User) -> Shared:
        """The person shares a resume in the conversation. It's kept and read in
        the background like any import, and Plytos answers with what it found
        once it's read. The file name comes in a header, never the URL."""
        data, filename = await read_upload(request)
        fmt = detect_format(data, filename)

        def store() -> Shared:
            with db.as_user(user_id) as conn:
                store = imports(conn, user_id)
                kept = store.keep(data, filename, fmt)
                message = agents(conn, user_id).share_resume(kept.id)
                return Shared(messages=[message], resume=store.summary(kept.id))

        return await run_in_threadpool(store)

    @app.get("/v1/proposals")
    def proposals(user_id: User, state: ProposalState | None = "open") -> list[ProposalView]:
        with db.as_user(user_id) as conn:
            return agents(conn, user_id).proposals(state)

    @app.post("/v1/proposals/{proposal_id}/keep", status_code=status.HTTP_201_CREATED)
    def keep(proposal_id: UUID, body: Keep, user_id: User) -> Kept:
        """Keeps a proposed card, as proposed or as the person edited it."""
        with db.as_user(user_id) as conn:
            proposal, card = agents(conn, user_id).keep(
                proposal_id, repo(conn, user_id), body.content
            )
        return Kept(proposal=proposal, card=card)

    @app.post("/v1/proposals/{proposal_id}/dismiss")
    def dismiss(proposal_id: UUID, user_id: User) -> ProposalView:
        with db.as_user(user_id) as conn:
            return agents(conn, user_id).dismiss(proposal_id)

    def resumes(conn: psycopg.Connection, user_id: UUID) -> tuple[ResumeStore, CardRepository]:
        cipher = vault.cipher_for(conn, user_id)
        return ResumeStore(conn, user_id, cipher), CardRepository(conn, user_id, cipher)

    def page(detail: ResumeDetail, cards: CardRepository) -> ResumePage:
        return ResumePage(resume=detail, page=render(detail.content, cards, detail.target_id))

    @app.get("/v1/resumes")
    def list_resumes(user_id: User) -> Resumes:
        """The person's resumes, newest change first, and the files a resume
        can still be made from as written."""
        with db.as_user(user_id) as conn:
            store, _ = resumes(conn, user_id)
            listed = store.summaries()
            made = {r.import_id for r in listed if r.import_id is not None}
            ready = [
                i for i in imports(conn, user_id).summaries() if i.approved > 0 and i.id not in made
            ]
            return Resumes(resumes=listed, ready=ready)

    @app.post("/v1/resumes/as-written", status_code=status.HTTP_201_CREATED)
    def make_as_written(body: MakeAsWritten, user_id: User) -> ResumePage:
        """Makes the person's resume as they wrote it, from the cards they kept
        from a file. Asking again for the same file returns the one made."""
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            if body.import_id in store.imported():
                made = next(r for r in store.summaries() if r.import_id == body.import_id)
                return page(store.detail(made.id), cards)
            view = imports(conn, user_id).get(body.import_id)
            if view.result is None:
                raise ImportConflictError("This resume is still being read.")
            content = as_written(view.result, view.progress, cards.main_contents())
            if not content.entries and not content.context:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "Keep some cards from this file first.",
                )
            detail = store.create("My resume", content, person(user_id), import_id=view.id)
            return page(detail, cards)

    @app.get("/v1/resumes/{resume_id}")
    def get_resume(resume_id: UUID, user_id: User) -> ResumePage:
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            return page(store.detail(resume_id), cards)

    @app.get("/v1/resumes/latest/contact")
    def latest_contact(user_id: User) -> LatestContact | None:
        """The contact details and highlights of the resume changed most
        recently, in one request. Null when there's no resume yet."""
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            head = store.latest_head()
            if head is None:
                return None
            return LatestContact(
                resume_id=head.resume_id,
                resume_name=head.name,
                base_version_id=head.version_id,
                header=head.content.header,
                highlights=render(head.content, cards, head.target_id).highlights,
            )

    @app.patch("/v1/resumes/{resume_id}")
    def rename_resume(resume_id: UUID, body: RenameResume, user_id: User) -> ResumeDetail:
        with db.as_user(user_id) as conn:
            store, _ = resumes(conn, user_id)
            return store.rename(resume_id, body.name)

    @app.post("/v1/resumes/{resume_id}/preview")
    def preview_resume(resume_id: UUID, body: ResumeContent, user_id: User) -> RenderedResume:
        """How a change would read, before the person saves it. Saves nothing."""
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            return render(body, cards, store.detail(resume_id).target_id)

    @app.post("/v1/resumes/{resume_id}/versions", status_code=status.HTTP_201_CREATED)
    def save_resume(resume_id: UUID, body: SaveResume, user_id: User) -> ResumePage:
        """Saves a change as a new version. Every version stays and can be restored."""
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            detail = store.save(resume_id, body.content, body.base_version_id, person(user_id))
            return page(detail, cards)

    @app.get("/v1/resumes/{resume_id}/versions/{number}")
    def get_resume_version(resume_id: UUID, number: int, user_id: User) -> ResumeVersionPage:
        """One earlier version, as it reads with the cards as they are now."""
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            target_id = store.detail(resume_id).target_id
            version, content = store.version(resume_id, number)
            return ResumeVersionPage(
                version=version, content=content, page=render(content, cards, target_id)
            )

    @app.post("/v1/resumes/{resume_id}/restore", status_code=status.HTTP_201_CREATED)
    def restore_resume(resume_id: UUID, body: RestoreResume, user_id: User) -> ResumePage:
        """Brings back an earlier version as a new one. Nothing is lost."""
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            detail = store.restore(resume_id, body.number, body.base_version_id, person(user_id))
            return page(detail, cards)

    @app.post("/v1/resumes/{resume_id}/versions/{number}/name")
    def name_resume_version(
        resume_id: UUID, number: int, body: NameVersion, user_id: User
    ) -> ResumeDetail:
        """Names a version, such as "Sent to Contoso"."""
        with db.as_user(user_id) as conn:
            store, _ = resumes(conn, user_id)
            return store.name_version(resume_id, number, body.name)

    @app.get("/v1/resumes/{resume_id}/versions/{number}/deletion")
    def plan_deletion(
        resume_id: UUID, number: int, user_id: User, after: bool = False
    ) -> DeletionPlan:
        """What deleting a version (with ``after``, and every one after it)
        would do, before the person confirms. Changes nothing."""
        with db.as_user(user_id) as conn:
            store, _ = resumes(conn, user_id)
            return store.plan_deletion(resume_id, number, after=after)

    @app.post("/v1/resumes/{resume_id}/versions/{number}/delete")
    def delete_versions(
        resume_id: UUID, number: int, body: DeleteVersions, user_id: User
    ) -> Deleted:
        """Deletes a version for good, and with ``after`` every one after it.
        What stays re-centers; see ResumeStore."""
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            detail = store.delete_versions(
                resume_id,
                number,
                body.base_version_id,
                person(user_id),
                after=body.after,
                with_branches=body.with_branches,
            )
            return Deleted(resume=page(detail, cards) if detail else None)

    @app.get("/v1/resumes/{resume_id}/parent-changes")
    def parent_changes(resume_id: UUID, user_id: User) -> ParentChanges:
        """Changes in the resume this one was made from that it hasn't taken."""
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            detail = store.detail(resume_id)
            parent_version = store.head_version_id(detail.parent_id) if detail.parent_id else None
            library = cards.main_contents()
            return ParentChanges(
                parent_version_id=parent_version,
                changes=[
                    LabeledChange(change=c, label=describe(c, library))
                    for c in store.parent_changes(resume_id, parent_version)
                ],
            )

    @app.post("/v1/resumes/{resume_id}/take", status_code=status.HTTP_201_CREATED)
    def take_changes(resume_id: UUID, body: TakeChanges, user_id: User) -> ResumePage:
        """Takes the chosen changes from the resume this one was made from, or
        passes on them all with no keys."""
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            detail = store.take(
                resume_id,
                body.keys,
                body.base_version_id,
                person(user_id),
                body.parent_version_id,
            )
            return page(detail, cards)

    @app.post("/v1/resumes/{resume_id}/copies", status_code=status.HTTP_201_CREATED)
    def copy_resume(resume_id: UUID, body: CopyResume, user_id: User) -> ResumePage:
        """Makes a version of a resume for a target by hand, without AI. It
        starts the same as the resume it's made from."""
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            source = store.detail(resume_id)
            target = cards.create_target(body.target_kind, body.target, None)
            content = source.content.model_copy(deep=True)
            if source.target_id is not None:
                content = keep_wording(content, source.target_id)
            content.note = None
            detail = store.create(
                body.name,
                content,
                person(user_id),
                target_id=target.id,
                parent_id=source.id,
                synced_parent_version_id=source.head.id,
            )
            return page(detail, cards)

    @app.post("/v1/resumes/{resume_id}/ask", status_code=status.HTTP_201_CREATED)
    def ask_for_version(resume_id: UUID, body: AskForVersion, user_id: User) -> MessageView:
        """Asks Plytos, in the conversation, for a version of this resume. The
        Assembler answers there with a proposal."""
        with db.as_user(user_id) as conn:
            store, _ = resumes(conn, user_id)
            store.head_version_id(resume_id)  # 404 if it isn't theirs
            return agents(conn, user_id).ask_for_resume(body.text, resume_id)

    @app.get("/v1/proposals/{proposal_id}/resume")
    def proposed_resume(proposal_id: UUID, user_id: User) -> ProposedResume:
        """A proposed resume as it would read, with the wording drafted for it."""
        with db.as_user(user_id) as conn:
            proposal = agents(conn, user_id).proposal(proposal_id)
            new = proposal.body.resume
            if new is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
            store, cards = resumes(conn, user_id)
            try:
                parent_name: str | None = store.detail(new.parent_id).name
            except ResumeNotFoundError:
                parent_name = None
            proposed = {r.card: r.framing for r in new.rewordings}
            return ProposedResume(
                proposal=proposal,
                parent_name=parent_name,
                page=render(new.content, cards, None, proposed),
            )

    @app.post("/v1/proposals/{proposal_id}/keep-resume", status_code=status.HTTP_201_CREATED)
    def keep_resume(proposal_id: UUID, body: KeepResume, user_id: User) -> KeptResume:
        """Keeps a proposed resume, as proposed or as the person changed it."""
        with db.as_user(user_id) as conn:
            store, cards = resumes(conn, user_id)
            proposal, resume = agents(conn, user_id).keep_resume(
                proposal_id, cards, store, body.content, body.rewordings
            )
            return KeptResume(proposal=proposal, resume=resume)

    def check_ins(store: AgentStore) -> CheckIns:
        plan = store.check_in_plan()
        return CheckIns(
            plan=plan,
            label=plan_label(plan) if plan else None,
            next_at=store.next_check_in(),
        )

    @app.get("/v1/check-ins")
    def get_check_ins(user_id: User) -> CheckIns:
        """When Plytos checks in, and when it's next due. No plan means the
        person hasn't been asked yet."""
        with db.as_user(user_id) as conn:
            return check_ins(agents(conn, user_id))

    @app.put("/v1/check-ins")
    def set_check_ins(body: CheckInPlan, user_id: User) -> CheckInsSet:
        """Sets when Plytos checks in, or turns check-ins off. Plytos says what
        changed in the conversation."""
        with db.as_user(user_id) as conn:
            store = agents(conn, user_id)
            try:
                store.set_check_in_plan(body)
            except CheckInPlanError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
            message = store.notice(plan_confirmation(body), "check_in")
            return CheckInsSet(check_ins=check_ins(store), message=message)

    @app.get("/v1/tidbits")
    def tidbits(user_id: User, card_id: UUID | None = None) -> list[TidbitView]:
        with db.as_user(user_id) as conn:
            return agents(conn, user_id).tidbits(card_id)

    @app.get("/v1/agent-runs")
    def agent_runs(user_id: User) -> list[RunView]:
        """What the agents did lately, for "how I got here". Never content."""
        with db.as_user(user_id) as conn:
            return agents(conn, user_id).runs()

    return app
