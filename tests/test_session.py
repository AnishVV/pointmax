import stat

import httpx
import pytest
import respx

from pointmax.sources.pointsyeah import session as s

AUTHED = {
    "data": {
        "isAuthenticated": True,
        "requestKeySection": "AbCd1234",
        "maxDateRange": 4,
        "user": {"userId": "u-1"},
    }
}


def _data():
    return s.SessionData(cookies=[{"name": "sid", "value": "abc", "domain": ".pointsyeah.com"}])


def test_parse_auth_finds_nested_keys():
    info = s.parse_auth(AUTHED)
    assert info.authenticated and info.request_key_section == "AbCd1234"
    assert info.max_date_range == 4 and info.user_id == "u-1"


def test_parse_auth_unauthenticated():
    assert not s.parse_auth({"data": {"isAuthenticated": False}}).authenticated
    assert not s.parse_auth({"data": {"isAuthenticated": True}}).authenticated  # no key section


def test_save_load_mode_600(tmp_path):
    p = tmp_path / "sub" / "session.json"
    s.save_session(_data(), p)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert s.load_session(p).cookies[0]["name"] == "sid"


def test_load_missing_and_corrupt(tmp_path):
    with pytest.raises(s.SessionError, match="pointmax login"):
        s.load_session(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(s.SessionError, match="unreadable"):
        s.load_session(bad)


def test_mask_and_dump_hide_secrets():
    assert s.mask("AbCd1234") == "Ab****34"
    d = _data().model_copy(update={"request_key_section": "AbCd1234"})
    out = s.dump(d)
    assert "abc" not in out and "AbCd1234" not in out


@respx.mock
async def test_ensure_session_refreshes_key_and_limits(tmp_path):
    p = tmp_path / "session.json"
    s.save_session(_data(), p)
    route = respx.get(s.AUTH_URL).mock(return_value=httpx.Response(200, json=AUTHED))
    got = await s.ensure_session(path=p)
    assert got.request_key_section == "AbCd1234" and got.max_date_range == 4
    assert route.calls.last.request.headers["cookie"].startswith("sid=abc")
    assert s.load_session(p).request_key_section == "AbCd1234"


@respx.mock
async def test_ensure_session_expired(tmp_path, monkeypatch):
    p = tmp_path / "session.json"
    s.save_session(_data(), p)
    monkeypatch.setenv("POINTMAX_HOME", str(tmp_path))  # no chrome profile -> no silent refresh
    respx.get(s.AUTH_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(s.SessionError, match="expired"):
        await s.ensure_session(path=p)
