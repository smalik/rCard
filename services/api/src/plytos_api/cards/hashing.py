"""Content hashes and the per-line hash chain.

Each version stores a hash of its content and a chain hash that also covers
its parent's chain hash, like git commits. The chain can be checked without
decrypting anything, and still checks out after a version is redacted.
Attestations (M3) will sign one exact version's chain hash.
"""

import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel

_ZERO = bytes(32)


def canonical_json(content: BaseModel) -> bytes:
    data: Any = content.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def content_hash(content: BaseModel) -> bytes:
    return hashlib.sha256(canonical_json(content)).digest()


def chain_hash(
    *,
    card_id: UUID,
    line_id: UUID,
    number: int,
    schema_version: int,
    parent_chain_hash: bytes | None,
    based_on_main_version_id: UUID | None,
    content_hash: bytes,
) -> bytes:
    h = hashlib.sha256(b"plytos.card_version.v1\n")
    h.update(card_id.bytes)
    h.update(line_id.bytes)
    h.update(number.to_bytes(8, "big"))
    h.update(schema_version.to_bytes(2, "big"))
    h.update(parent_chain_hash or _ZERO)
    h.update(based_on_main_version_id.bytes if based_on_main_version_id else _ZERO[:16])
    h.update(content_hash)
    return h.digest()
