import json

from pointmax.devtools import scrub
from pointmax.sources.pointsyeah import crypto

SECTION = "AbCd1234"
USER_ID = "user-8f3a9c"
EMAIL = "someone@example.com"


def _entry(t, url, req=None, resp=None):
    return {
        "t": t,
        "at": "2026-10-02T00:00:00+00:00",
        "method": "POST",
        "url": url,
        "status": 200,
        "request_headers": {"user-agent": "Chrome"},
        "request_body": None if req is None else json.dumps(req),
        "response_body": json.dumps(resp),
    }


def _capture(tmp_path):
    query = {"search_type": "one_way", "segments": [{"from": "DFW", "to": "LHR"}], "uid": USER_ID}
    text = crypto.serialize(query)
    enc = crypto.encrypt_text(text, SECTION)
    entries = [
        _entry(
            0,
            "https://www.pointsyeah.com/api/auth/session",
            resp={
                "data": {
                    "isAuthenticated": True,
                    "requestKeySection": SECTION,
                    "userId": USER_ID,
                    "email": EMAIL,
                    "name": "Test Person",
                }
            },
        ),
        _entry(
            1,
            "https://api2.pointsyeah.com/flight/search/create_task",
            req={"data": enc, "encrypted": enc},
            resp={"code": 0, "data": {"task_id": "T1", "total_sub_tasks": 2}},
        ),
        _entry(
            3,
            "https://api2.pointsyeah.com/flight/search/fetch_result",
            req={"task_id": "T1"},
            resp={"data": {"status": "processing", "result": [{"note": f"by {EMAIL}"}]}},
        ),
        _entry(
            5,
            "https://api2.pointsyeah.com/flight/search/fetch_result",
            req={"task_id": "OTHER"},
            resp={"data": {"status": "done"}},
        ),
        _entry(
            9,
            "https://api2.pointsyeah.com/flight/search/fetch_result",
            req={"task_id": "T1"},
            resp={"data": {"status": "done", "result": []}},
        ),
    ]
    path = tmp_path / "traffic.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return path


def test_build_fixtures(tmp_path):
    out = tmp_path / "fixtures"
    scrub.build_fixtures(_capture(tmp_path), out, ["dfw-lhr"])

    meta = json.loads((out / "dfw-lhr" / "meta.json").read_text())
    assert meta["browser_byte_match"] and meta["reencrypt_match"]
    assert meta["total_sub_tasks"] == 2
    assert meta["polls"] == 2

    polls = [
        json.loads(line)
        for line in (out / "dfw-lhr" / "fetch_result.jsonl").read_text().splitlines()
    ]
    assert [p["t"] for p in polls] == [2, 8]

    everything = "".join(f.read_text() for f in out.rglob("*") if f.is_file())
    for secret in (SECTION, USER_ID, EMAIL, "Test Person"):
        assert secret not in everything

    kat = json.loads((out / "crypto_kat.json").read_text())
    assert len(kat["section"]) == len(SECTION)
    assert crypto.decrypt_text(kat["ciphertext"], kat["section"]) == kat["plaintext"]
    assert kat["live_data_ciphertext"] is None  # plaintext carried an identifier
