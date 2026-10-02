"""Login, session storage and validation for PointsYeah.

Response field names of /api/auth/session (`isAuthenticated`, `requestKeySection`, `userId`,
`maxDateRange`) come from the plan's recon notes and are located anywhere in the JSON tree, so
a nesting change does not break us. VERIFY against a live response in M1.
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from pointmax import config

BASE_URL = "https://www.pointsyeah.com"
AUTH_URL = f"{BASE_URL}/api/auth/session"
COOKIE_DOMAIN = "pointsyeah.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
LOGIN_TIMEOUT_S = 300
LOGIN_POLL_S = 2.0


class SessionError(RuntimeError):
    """The session is missing, expired or unusable; the message says what to do."""


class SessionData(BaseModel):
    cookies: list[dict[str, Any]] = Field(default_factory=list)
    request_key_section: str = ""
    user_id: str = ""
    max_date_range: int | None = None
    user_agent: str = DEFAULT_USER_AGENT
    saved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def cookie_header(self) -> str:
        return "; ".join(f"{c['name']}={c['value']}" for c in self.cookies)

    @property
    def age_hours(self) -> float:
        return (datetime.now(UTC) - self.saved_at).total_seconds() / 3600


@dataclass(frozen=True)
class AuthInfo:
    authenticated: bool
    request_key_section: str = ""
    user_id: str = ""
    max_date_range: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def find_key(obj: Any, key: str) -> Any:
    """First value stored under `key` anywhere in a JSON tree."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        children = list(obj.values())
    elif isinstance(obj, list):
        children = obj
    else:
        return None
    for child in children:
        if (hit := find_key(child, key)) is not None:
            return hit
    return None


def parse_auth(payload: Any) -> AuthInfo:
    authed = find_key(payload, "isAuthenticated")
    section = find_key(payload, "requestKeySection")
    mdr = find_key(payload, "maxDateRange")
    uid = find_key(payload, "userId")
    return AuthInfo(
        authenticated=bool(authed) and bool(section),
        request_key_section=str(section or ""),
        user_id=str(uid or ""),
        max_date_range=int(mdr)
        if isinstance(mdr, int | float | str) and str(mdr).isdigit()
        else None,
        raw=payload if isinstance(payload, dict) else {},
    )


# ---- storage -----------------------------------------------------------------------------


def save_session(data: SessionData, path: Path | None = None) -> Path:
    path = path or config.session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(data.model_dump_json(indent=2))
    os.replace(tmp, path)
    path.chmod(0o600)
    return path


def load_session(path: Path | None = None) -> SessionData:
    path = path or config.session_path()
    try:
        return SessionData.model_validate_json(path.read_text())
    except FileNotFoundError:
        raise SessionError("No session found. Run `pointmax login`.") from None
    except ValueError as e:
        raise SessionError(f"Session file {path} is unreadable ({e}). Run `pointmax login`.") from e


def mask(secret: str, keep: int = 2) -> str:
    return (
        secret
        if len(secret) <= keep * 2
        else f"{secret[:keep]}{'*' * (len(secret) - keep * 2)}{secret[-keep:]}"
    )


# ---- validation --------------------------------------------------------------------------


async def check_session(data: SessionData, client: httpx.AsyncClient | None = None) -> AuthInfo:
    """GET /api/auth/session with the saved cookies."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=20, follow_redirects=True)
    try:
        resp = await client.get(
            AUTH_URL,
            headers={
                "User-Agent": data.user_agent,
                "Referer": f"{BASE_URL}/",
                "Cookie": data.cookie_header(),
            },
        )
        if resp.status_code in (401, 403):
            return AuthInfo(authenticated=False)
        resp.raise_for_status()
        return parse_auth(resp.json())
    finally:
        if own:
            await client.aclose()


async def auth_exchange(data: SessionData) -> dict[str, Any]:
    """The raw /api/auth/session exchange, for --save-raw (scrub needs the key section)."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(
            AUTH_URL,
            headers={"User-Agent": data.user_agent, "Cookie": data.cookie_header()},
        )
    return {
        "t": 0.0,
        "at": datetime.now(UTC).isoformat(),
        "method": "GET",
        "url": AUTH_URL,
        "status": resp.status_code,
        "request_headers": {"user-agent": data.user_agent},
        "request_body": None,
        "response_body": resp.text,
    }


def apply_auth(data: SessionData, info: AuthInfo) -> SessionData:
    """Fresh key section and plan limits are always taken from the live response."""
    return data.model_copy(
        update={
            "request_key_section": info.request_key_section or data.request_key_section,
            "user_id": info.user_id or data.user_id,
            "max_date_range": info.max_date_range or data.max_date_range,
            "saved_at": datetime.now(UTC),
        }
    )


async def ensure_session(
    client: httpx.AsyncClient | None = None, *, path: Path | None = None, refresh: bool = True
) -> SessionData:
    """Load, validate and refresh the saved session, or raise SessionError."""
    data = load_session(path)
    info = await check_session(data, client)
    if not info.authenticated and refresh:
        data = await silent_refresh(data)
        info = await check_session(data, client)
    if not info.authenticated:
        raise SessionError("Session expired. Run `pointmax login`.")
    data = apply_auth(data, info)
    save_session(data, path)
    return data


# ---- login paths (need a real browser; not exercised offline) -----------------------------


def _cookies_to_dicts(cookies: Any) -> list[dict[str, Any]]:
    out = []
    for c in cookies:
        out.append(
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path or "/",
                "expires": c.expires,
                "secure": bool(c.secure),
            }
        )
    return out


async def login_from_chrome() -> SessionData:
    """Fallback: import PointsYeah cookies from your everyday Chrome (browser_cookie3)."""
    import browser_cookie3

    try:
        jar = browser_cookie3.chrome(domain_name=COOKIE_DOMAIN)
    except Exception as e:  # keychain denied, no profile, locked DB ...
        raise SessionError(f"Could not read Chrome cookies: {e}") from e
    data = SessionData(cookies=_cookies_to_dicts(jar))
    if not data.cookies:
        raise SessionError("No pointsyeah.com cookies in Chrome. Sign in there first.")
    info = await check_session(data)
    if not info.authenticated:
        raise SessionError("Chrome's PointsYeah cookies are not signed in. Sign in there first.")
    return apply_auth(data, info)


async def _launch(pw: Any, *, headless: bool) -> Any:
    profile = config.chrome_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    return await pw.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        channel="chrome",
        headless=headless,
        ignore_default_args=["--enable-automation"],
        args=["--disable-blink-features=AutomationControlled"],
    )


async def _page_auth(page: Any) -> AuthInfo:
    payload = await page.evaluate(
        "() => fetch('/api/auth/session', {credentials: 'include'}).then(r => r.json())"
    )
    return parse_auth(payload)


async def _harvest(ctx: Any, page: Any, info: AuthInfo) -> SessionData:
    cookies = [c for c in await ctx.cookies() if COOKIE_DOMAIN in c.get("domain", "")]
    ua = await page.evaluate("() => navigator.userAgent")
    return apply_auth(SessionData(cookies=cookies, user_agent=ua or DEFAULT_USER_AGENT), info)


async def login_browser(*, timeout_s: float = LOGIN_TIMEOUT_S) -> SessionData:
    """Primary path: headed real Chrome with a persistent profile; you finish SSO yourself."""
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        ctx = await _launch(pw, headless=False)
        try:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(f"{BASE_URL}/")
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                try:
                    info = await _page_auth(page)
                except Exception:  # page mid-navigation during SSO
                    info = AuthInfo(authenticated=False)
                if info.authenticated:
                    return await _harvest(ctx, page, info)
                await page.wait_for_timeout(int(LOGIN_POLL_S * 1000))
            raise SessionError(f"Timed out after {timeout_s:.0f}s waiting for sign-in.")
        finally:
            await ctx.close()


async def silent_refresh(data: SessionData) -> SessionData:
    """Relaunch the persistent profile headless and re-read cookies; keeps old data on failure."""
    if not config.chrome_profile_dir().exists():
        return data
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            ctx = await _launch(pw, headless=True)
            try:
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.goto(f"{BASE_URL}/")
                info = await _page_auth(page)
                if info.authenticated:
                    return await _harvest(ctx, page, info)
            finally:
                await ctx.close()
    except Exception:
        pass
    return data


def dump(data: SessionData) -> str:
    """Safe summary for logs: never the cookie values."""
    return json.dumps(
        {
            "cookies": [c["name"] for c in data.cookies],
            "key_section": mask(data.request_key_section),
            "max_date_range": data.max_date_range,
        }
    )
