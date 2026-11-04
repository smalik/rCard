"""Per-person encryption keys.

Each person has a random 256-bit data key (DEK). It is stored only in wrapped
form, encrypted by a key-encryption key (KEK) that lives in Cloud KMS in
production. Card content is encrypted with the person's DEK. Deleting the
wrapped DEK makes every copy of that person's content unreadable, which is how
account deletion reaches backups (crypto-shredding).
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Any, Protocol
from uuid import UUID

import psycopg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_FORMAT_V1 = b"\x01"
_NONCE_BYTES = 12


class KeyShreddedError(Exception):
    """The person's data key is gone, so their content can't be read."""


class KeyEncryptionKey(Protocol):
    name: str

    def wrap(self, dek: bytes, aad: bytes) -> bytes: ...

    def unwrap(self, wrapped: bytes, aad: bytes) -> bytes: ...


class LocalKek:
    """A KEK held in process memory. Only for development and tests."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("local KEK must be 32 bytes")
        self._aead = AESGCM(key)
        self.name = "local:" + hashlib.sha256(key).hexdigest()[:16]

    def wrap(self, dek: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        return nonce + self._aead.encrypt(nonce, dek, aad)

    def unwrap(self, wrapped: bytes, aad: bytes) -> bytes:
        return self._aead.decrypt(wrapped[:_NONCE_BYTES], wrapped[_NONCE_BYTES:], aad)


class CloudKmsKek:
    """A KEK in Cloud KMS. The key material never leaves KMS."""

    def __init__(self, key_name: str) -> None:
        self._client: Any = None
        self._key_name = key_name
        self.name = "gcp-kms:" + key_name

    def _kms(self) -> Any:
        if self._client is None:
            from google.cloud import kms

            self._client = kms.KeyManagementServiceClient()
        return self._client

    def wrap(self, dek: bytes, aad: bytes) -> bytes:
        response = self._kms().encrypt(
            request={"name": self._key_name, "plaintext": dek, "additional_authenticated_data": aad}
        )
        return bytes(response.ciphertext)

    def unwrap(self, wrapped: bytes, aad: bytes) -> bytes:
        response = self._kms().decrypt(
            request={
                "name": self._key_name,
                "ciphertext": wrapped,
                "additional_authenticated_data": aad,
            }
        )
        return bytes(response.plaintext)


def kek_from_setting(value: str, *, allow_local: bool) -> KeyEncryptionKey:
    scheme, _, rest = value.partition(":")
    if scheme == "local":
        if not allow_local:
            raise ValueError("a local KEK is only allowed in dev and test")
        return LocalKek(base64.b64decode(rest))
    if scheme == "gcp-kms":
        return CloudKmsKek(rest)
    raise ValueError("PLYTOS_KEK must start with local: or gcp-kms:")


class UserCipher:
    """Encrypts and decrypts one person's content with their data key."""

    def __init__(self, dek: bytes) -> None:
        self._aead = AESGCM(dek)

    def encrypt(self, plaintext: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        return _FORMAT_V1 + nonce + self._aead.encrypt(nonce, plaintext, aad)

    def decrypt(self, blob: bytes, aad: bytes) -> bytes:
        if blob[:1] != _FORMAT_V1:
            raise ValueError("unknown ciphertext format")
        nonce = blob[1 : 1 + _NONCE_BYTES]
        return self._aead.decrypt(nonce, blob[1 + _NONCE_BYTES :], aad)


def _key_aad(user_id: UUID) -> bytes:
    return b"plytos.user_key:" + user_id.bytes


class Vault:
    """Creates and loads per-person data keys. Callers pass a connection that
    is already scoped to the person (see Database.as_user)."""

    def __init__(self, kek: KeyEncryptionKey) -> None:
        self._kek = kek

    def create_user_key(self, conn: psycopg.Connection, user_id: UUID) -> UserCipher:
        dek = AESGCM.generate_key(bit_length=256)
        wrapped = self._kek.wrap(dek, _key_aad(user_id))
        conn.execute(
            "insert into vault.user_key (user_id, kek_name, wrapped_dek) values (%s, %s, %s)",
            (user_id, self._kek.name, wrapped),
        )
        return UserCipher(dek)

    def cipher_for(self, conn: psycopg.Connection, user_id: UUID) -> UserCipher:
        row = conn.execute(
            "select wrapped_dek from vault.user_key where user_id = %s", (user_id,)
        ).fetchone()
        if row is None:
            raise KeyShreddedError(str(user_id))
        return UserCipher(self._kek.unwrap(bytes(row[0]), _key_aad(user_id)))
