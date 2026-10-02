"""Query encryption for create_task (recipe from recon; validated live in M2).

`key(section) = b64decode("LefjQ2pEXmiy/nNZvhJ43i8" + section + "YHYbn1hOuAgA=")`, a fixed IV,
CBC with PKCS7. The AES variant follows the decoded key length: an 8-character section gives
a 32-byte key (AES-256), so the cipher is not hard-coded to AES-128.
"""

import base64
import json
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KEY_PREFIX = "LefjQ2pEXmiy/nNZvhJ43i8"
KEY_SUFFIX = "YHYbn1hOuAgA="
IV = b"1020304050607080"


def derive_key(section: str) -> bytes:
    try:
        key = base64.b64decode(f"{KEY_PREFIX}{section}{KEY_SUFFIX}", validate=True)
    except ValueError as e:
        raise ValueError(f"requestKeySection {section!r} does not give a valid base64 key") from e
    if len(key) not in (16, 24, 32):
        raise ValueError(f"derived key is {len(key)} bytes; AES needs 16, 24 or 32")
    return key


def serialize(query: Any) -> str:
    """Compact JSON, as the browser's JSON.stringify produces it."""
    return json.dumps(query, separators=(",", ":"), ensure_ascii=False)


def encrypt_text(plaintext: str, section: str) -> str:
    padder = padding.PKCS7(128).padder()
    data = padder.update(plaintext.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(derive_key(section)), modes.CBC(IV)).encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode()


def decrypt_text(ciphertext: str, section: str) -> str:
    dec = Cipher(algorithms.AES(derive_key(section)), modes.CBC(IV)).decryptor()
    padded = dec.update(base64.b64decode(ciphertext)) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode()


def encrypt_query(query: Any, section: str) -> str:
    return encrypt_text(serialize(query), section)
