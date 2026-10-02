"""Turn a raw capture from `pointmax.devtools.record` into committable test fixtures.

    uv run python -m pointmax.devtools.scrub captures/<stamp> --labels dfw-lhr,dfw-amd,multi

For each create_task in the capture (in order) it writes `tests/fixtures/<label>/` with the
decrypted, scrubbed query, the create_task response and every fetch_result poll in order.
It also writes `tests/fixtures/crypto_kat.json`: the live ciphertext is decrypted with your
real `requestKeySection`, the plaintext is checked to be byte-identical to our compact
serialization, then re-encrypted under a dummy section so no account secret is committed.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from pointmax.sources.pointsyeah import crypto

SENSITIVE_KEY = re.compile(
    r"e-?mail|token|cookie|password|phone|user_?id|uid|account|avatar|image|key_?section",
    re.IGNORECASE,
)
REDACTED = "<scrubbed>"
DUMMY_SECTION_CHARS = "pmTESTsection0123456789ABCDEFGH"


def _loads(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def find_key(obj: Any, key: str) -> Any:
    """First value stored under `key` anywhere in a JSON tree."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        children = obj.values()
    elif isinstance(obj, list):
        children = obj
    else:
        return None
    for child in children:
        if (hit := find_key(child, key)) is not None:
            return hit
    return None


def identity_values(session_json: Any) -> set[str]:
    """Strings in the auth-session response that identify the account."""
    found: set[str] = set()

    def walk(obj: Any, key: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, k)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, key)
        elif (
            isinstance(obj, str | int)
            and not isinstance(obj, bool)
            and len(str(obj)) >= 4
            and (SENSITIVE_KEY.search(key) or re.search(r"name|^id$|^sub$", key, re.I))
        ):
            found.add(str(obj))

    walk(session_json)
    return found


def scrub(obj: Any, identities: set[str]) -> Any:
    if isinstance(obj, dict):
        return {
            k: REDACTED if SENSITIVE_KEY.search(k) and v not in (None, "") else scrub(v, identities)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [scrub(v, identities) for v in obj]
    if isinstance(obj, str):
        for ident in identities:
            obj = obj.replace(ident, REDACTED)
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool) and str(obj) in identities:
        return REDACTED
    return obj


def dummy_section(real: str) -> str:
    return (DUMMY_SECTION_CHARS * (len(real) // len(DUMMY_SECTION_CHARS) + 1))[: len(real)]


def build_fixtures(capture: Path, out: Path, labels: list[str]) -> list[Path]:
    entries = [
        json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines() if line
    ]
    sessions = [_loads(e["response_body"]) for e in entries if "/api/auth/session" in e["url"]]
    sessions = [s for s in sessions if find_key(s, "requestKeySection")]
    if not sessions:
        sys.exit(
            "No authenticated /api/auth/session response in the capture; log in and re-record."
        )
    section = str(find_key(sessions[-1], "requestKeySection"))
    identities = set().union(*(identity_values(s) for s in sessions)) | {section}

    creates = [e for e in entries if "/flight/search/create_task" in e["url"]]
    polls = [e for e in entries if "/flight/search/fetch_result" in e["url"]]
    written: list[Path] = []
    kat: dict[str, Any] | None = None

    for i, ct in enumerate(creates):
        label = labels[i] if i < len(labels) else f"task-{i + 1}"
        req = _loads(ct["request_body"]) or {}
        resp = _loads(ct["response_body"])
        task_id = find_key(resp, "task_id")
        plaintext = crypto.decrypt_text(req["encrypted"], section)
        query = json.loads(plaintext)
        byte_match = crypto.serialize(query) == plaintext
        reencrypt_match = crypto.encrypt_text(plaintext, section) == req["encrypted"]
        leaks = any(ident in plaintext for ident in identities if ident != section)
        clean_query = scrub(query, identities)

        task_polls = [
            p
            for p in polls
            if task_id is not None and find_key(_loads(p["request_body"]), "task_id") == task_id
        ]
        d = out / label
        d.mkdir(parents=True, exist_ok=True)
        meta = {
            "label": label,
            "captured_at": ct["at"],
            "task_id": REDACTED if task_id is None else str(task_id),
            "total_sub_tasks": find_key(resp, "total_sub_tasks"),
            "polls": len(task_polls),
            "browser_byte_match": byte_match,
            "reencrypt_match": reencrypt_match,
            "data_equals_encrypted": req.get("data") == req.get("encrypted"),
            "request_headers": ct["request_headers"],
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
        (d / "query.json").write_text(json.dumps(clean_query, indent=2) + "\n")
        (d / "create_task.json").write_text(
            json.dumps({"status": ct["status"], "body": scrub(resp, identities)}, indent=2) + "\n"
        )
        with (d / "fetch_result.jsonl").open("w", encoding="utf-8") as fh:
            for p in task_polls:
                body = scrub(_loads(p["response_body"]), identities)
                rec = {"t": round(p["t"] - ct["t"], 3), "status": p["status"], "body": body}
                fh.write(json.dumps(rec) + "\n")
        written.append(d)

        if kat is None and byte_match:
            dummy = dummy_section(section)
            clean_text = crypto.serialize(clean_query)
            kat = {
                "note": "Live create_task plaintext, re-encrypted under a dummy section.",
                "source_fixture": label,
                "section": dummy,
                "plaintext": clean_text,
                "ciphertext": crypto.encrypt_text(clean_text, dummy),
                "browser_byte_match": True,
                # `data` uses the bundle's default key; keep it for M2 only if it can't leak.
                "live_data_ciphertext": None if leaks else req.get("data"),
            }
        print(
            f"{label}: task {meta['task_id']}, {len(task_polls)} polls, "
            f"byte match {byte_match}, re-encrypt match {reencrypt_match}"
        )

    if kat:
        (out / "crypto_kat.json").write_text(json.dumps(kat, indent=2) + "\n")
        written.append(out / "crypto_kat.json")

    for path in written:
        files = [path] if path.is_file() else list(path.iterdir())
        for f in files:
            text = f.read_text(encoding="utf-8")
            if any(ident in text for ident in identities):
                sys.exit(f"Identifier still present in {f}; fixture not safe to commit.")
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("capture", type=Path, help="captures/<stamp> directory or traffic.jsonl")
    ap.add_argument("--labels", default="", help="comma-separated fixture names, in task order")
    ap.add_argument("--out", type=Path, default=Path("tests/fixtures"))
    args = ap.parse_args()
    capture = args.capture / "traffic.jsonl" if args.capture.is_dir() else args.capture
    labels = [s.strip() for s in args.labels.split(",") if s.strip()]
    build_fixtures(capture, args.out, labels)


if __name__ == "__main__":
    main()
