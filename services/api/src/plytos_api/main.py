"""HTTP API. Only the web app's server calls it; it is never public."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import unquote
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from plytos_api.auth import resolve_user
from plytos_api.cards.model import CardKind, MainContent, TargetKind, VariantContent
from plytos_api.cards.repository import (
    Author,
    CardDetail,
    CardNotFoundError,
    CardRepository,
    CardSummary,
    SaveResult,
    StaleHeadError,
    TargetView,
    UnsupportedClaimsError,
    VariantExistsError,
    VersionView,
)
from plytos_api.config import Settings, get_settings
from plytos_api.db import Database
from plytos_api.imports.extract import MAX_BYTES, UnsupportedFileError
from plytos_api.imports.model import ImportResult
from plytos_api.imports.pipeline import import_resume
from plytos_api.keys import KeyShreddedError, Vault, kek_from_setting

FILENAME_HEADER = "x-plytos-filename"

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


class AcceptImport(BaseModel):
    cards: list[CreateCard] = Field(min_length=1, max_length=300)


class Verification(BaseModel):
    ok: bool
    problems: list[str]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.database_url)
    vault = Vault(kek_from_setting(settings.kek, allow_local=settings.dev_shortcuts))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.open()
        try:
            yield
        finally:
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

    @app.exception_handler(VariantExistsError)
    async def variant_exists(_: Request, __: VariantExistsError) -> JSONResponse:
        return JSONResponse(
            {"detail": "This card already has a variant for that target."},
            status_code=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(UnsupportedFileError)
    async def unsupported_file(_: Request, exc: UnsupportedFileError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)

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

    @app.post("/v1/imports/preview")
    async def preview_import(request: Request, user_id: User) -> ImportResult:
        """Reads a resume and returns proposed cards and an audit. Nothing is stored.

        The body is the file itself. The file name comes in a header, not the
        URL, because URLs land in request logs and resume file names carry names.
        """
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
        return await run_in_threadpool(import_resume, bytes(data), filename)

    @app.post("/v1/imports/accept", status_code=status.HTTP_201_CREATED)
    def accept_import(body: AcceptImport, user_id: User) -> list[CardDetail]:
        """Saves the cards the person kept from an import, all or none."""
        with db.as_user(user_id) as conn:
            cards = repo(conn, user_id)
            return [cards.create_card(c.kind, c.content, person(user_id)) for c in body.cards]

    return app
