import json
from pathlib import Path

import pytest

from pointmax.sources.pointsyeah import crypto

FIXTURES = Path(__file__).parent / "fixtures"
SECTION = "pmTESTse"  # 8 chars -> 32-byte key


def test_key_length():
    assert len(crypto.derive_key(SECTION)) == 32


def test_serialize_is_compact_and_ordered():
    assert crypto.serialize({"b": 1, "a": [1, 2], "c": "é"}) == '{"b":1,"a":[1,2],"c":"é"}'


def test_round_trip():
    query = {"search_type": "one_way", "cabins": ["Economy", "Business"], "adults": 1}
    ct = crypto.encrypt_query(query, SECTION)
    assert json.loads(crypto.decrypt_text(ct, SECTION)) == query


def test_encryption_is_deterministic():
    assert crypto.encrypt_text("x", SECTION) == crypto.encrypt_text("x", SECTION)


@pytest.mark.skipif(not (FIXTURES / "crypto_kat.json").exists(), reason="no live KAT recorded yet")
def test_known_answer():
    kat = json.loads((FIXTURES / "crypto_kat.json").read_text())
    assert kat["browser_byte_match"]
    assert crypto.serialize(json.loads(kat["plaintext"])) == kat["plaintext"]
    assert crypto.encrypt_text(kat["plaintext"], kat["section"]) == kat["ciphertext"]


def test_invalid_section_gives_clear_error():
    with pytest.raises(ValueError, match="requestKeySection"):
        crypto.derive_key("not base64!")
    with pytest.raises(ValueError, match="AES needs"):
        crypto.derive_key("AAAA")  # decodes to a key whose length is not 16/24/32
