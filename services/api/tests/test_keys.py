import os

import pytest
from cryptography.exceptions import InvalidTag

from plytos_api.keys import LocalKek, UserCipher, kek_from_setting


def test_wrap_round_trip_and_aad_binding() -> None:
    kek = LocalKek(os.urandom(32))
    dek = os.urandom(32)
    wrapped = kek.wrap(dek, b"user-a")
    assert kek.unwrap(wrapped, b"user-a") == dek
    with pytest.raises(InvalidTag):
        kek.unwrap(wrapped, b"user-b")


def test_user_cipher_round_trip_and_aad_binding() -> None:
    cipher = UserCipher(os.urandom(32))
    blob = cipher.encrypt(b"Finance Manager at Acme", b"row-1")
    assert b"Acme" not in blob
    assert cipher.decrypt(blob, b"row-1") == b"Finance Manager at Acme"
    with pytest.raises(InvalidTag):
        cipher.decrypt(blob, b"row-2")


def test_local_kek_is_refused_outside_dev_and_test() -> None:
    with pytest.raises(ValueError, match="only allowed in dev and test"):
        kek_from_setting("local:" + "A" * 44, allow_local=False)
    with pytest.raises(ValueError, match="must start with"):
        kek_from_setting("plaintext-key", allow_local=True)
