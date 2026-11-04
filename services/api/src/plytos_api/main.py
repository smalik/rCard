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

from plytos_api.agents.crew import crew
from plytos_api.agents.model import (
    MAX_MESSAGE,
    MessageView,
    ProposalState,
    ProposalView,
    RunView,
    TidbitView,
)
from plytos_api.agents.resume import reading
from plytos_api.agents.runtime import BackgroundWorker, Worker
from plytos_api.agents.store import AgentRecordNotFoundError, AgentStore, ProposalConflictError
from plytos_api.auth import resolve_user
from plytos_api.cards.model import CardKind, MainContent, TargetKind, VariantContent
from plytos_api.cards.repository import (
    Author,
    CardDetail,
    CardNotFoundError,
    CardRepository,
    CardSummary,
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
from plytos_api.imports.extract import MAX_BYTES, UnsupportedFileError
from plytos_api.imports.pipeline import import_resume
from plytos_api.imports.store import (
    ImportConflictError,
    ImportNotFoundError,
    ImportProgress,
    ImportStore,
    ImportSummary,
    ImportView,
)
from plytos_api.keys import KeyShreddedError, Vault, kek_from_setting

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


class SaveMainVersion(BaseModel):
    base_version_id: UUID
    content: MainContent


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


class Settle(BaseModel):
    finding: int = Field(ge=0)
    answer: Literal["chosen", "as_is", "on_card", "later"]
    value: str | None = Field(default=None, max_length=40)


class Decide(BaseModel):
    state: Literal["later", "dropped", "pending"]


class Approve(BaseModel):
    content: MainContent | None = None


class Approved(BaseModel):
    card: CardDetail
    progress: ImportProgress


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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.database_url)
    vault = Vault(kek_from_setting(settings.kek, allow_local=settings.dev_shortcuts))
    reader = reader_for(
        settings.ai_provider,
        settings.ai_model,
        settings.ai_effort,
        settings.ai_vertex_project,
        settings.ai_vertex_region,
    )

    background = (
        BackgroundWorker(Worker(db, vault, crew(settings))) if settings.agents_inline else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.open()
        if background:
            background.start()
        try:
            yield
        finally:
            if background:
                background.stop()
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

    @app.exception_handler(KeyShreddedError)
    async def shredded(_: Request, __: KeyShreddedError) -> JSONResponse:
        return JSONResponse({"detail": "Gone"}, status_code=status.HTTP_410_GONE)

    User = Annotated[UUID, Depends(resolve_user)]

    def repo(conn: psycopg.Connection, user_id: UUID) -> CardRepository:
        return CardRepository(conn, user_id, vault.cipher_for(conn, user_id))

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

    @app.post("/v1/imports", status_code=status.HTTP_201_CREATED)
    async def create_import(request: Request, user_id: User) -> ImportView:
        """Reads a resume, keeps the original encrypted, and returns proposed cards
        and an audit. No card is saved until the person approves it.

        The body is the file itself. The file name comes in a header, not the
        URL, because URLs land in request logs and resume file names carry names.
        """
        data, filename = await read_upload(request)
        result = await run_in_threadpool(import_resume, data, filename, reader=reader)

        def store() -> ImportView:
            with db.as_user(user_id) as conn:
                return imports(conn, user_id).create(data, filename, result)

        return await run_in_threadpool(store)

    @app.get("/v1/imports")
    def list_imports(user_id: User) -> list[ImportSummary]:
        with db.as_user(user_id) as conn:
            return imports(conn, user_id).summaries()

    @app.get("/v1/imports/{import_id}")
    def get_import(import_id: UUID, user_id: User) -> ImportView:
        with db.as_user(user_id) as conn:
            return imports(conn, user_id).get(import_id)

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

    @app.post("/v1/imports/{import_id}/cards/{ref}/approve", status_code=status.HTTP_201_CREATED)
    def approve(import_id: UUID, ref: CardRef, body: Approve, user_id: User) -> Approved:
        """Saves one proposed card as an approved card. AI never calls this: the
        wording is the person's own, from their resume or as they edited it."""
        with db.as_user(user_id) as conn:
            card, progress = imports(conn, user_id).approve(
                import_id, ref, body.content, repo(conn, user_id), person(user_id)
            )
        return Approved(card=card, progress=progress)

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
        """The person shares a resume in the conversation. It's read and kept like
        any import, and Plytos answers with what it found. The file name comes in
        a header, never the URL."""
        data, filename = await read_upload(request)
        result = await run_in_threadpool(import_resume, data, filename, reader=reader)

        def store() -> Shared:
            with db.as_user(user_id) as conn:
                store = imports(conn, user_id)
                kept = store.create(data, filename, result)
                messages = agents(conn, user_id).share_resume(kept.id, reading(result))
                return Shared(messages=messages, resume=store.summary(kept.id))

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
