"""Login utilities for ExpertOption API playwright."""
from __future__ import annotations
import asyncio
import base64
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from loguru import logger
from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Page,
    WebSocket,
    BrowserContext,
)
from .config import Config
from .constants import REGIONS
from .monitoring import error_monitor, ErrorSeverity, ErrorCategory

logger.remove()
logger.add(f"log-{time.strftime('%Y-%m-%d')}.txt", level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

EO_LOGIN = "https://expertoption.com/login"
EO_APP = "https://app.expertoption.com"
SESSION_DIR = Path("sessions")
SESSION_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_32HEX_RE = r"[A-Fa-f0-9]{32}"
WS_URL_HINT = "expertoption.com"

def load_config() -> Dict[str, Any]:
    try:
        return Config().load_config()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}

def save_config(config_data: Dict[str, Any]) -> None:
    try:
        Config().save_config(config_data)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")

def save_session(session: Dict[str, Any]) -> None:
    try:
        Config().save_session(session)
        logger.info("Session saved successfully")
    except Exception as e:
        logger.error(f"Failed to save session: {e}")

def _load_session() -> Dict[str, Any]:
    try:
        data = Config().session_data or {}
        if isinstance(data, dict):
            return data.copy()
        return {}
    except Exception:
        return {}

def _clear_session_file() -> None:
    try:
        sess_path = Config().session_file
        if sess_path and Path(sess_path).exists():
            Path(sess_path).unlink(missing_ok=True)
            logger.info("Invalid/expired session removed (session.json).")
    except Exception as e:
        logger.warning(f"Failed to remove session.json: {e}")

_STEALTH_JS = r"""
(() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
  Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
  window.chrome = { runtime: {} };
  const origQuery = navigator.permissions && navigator.permissions.query;
  if (origQuery) {
    navigator.permissions.query = (p) => (
      p && p.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) : origQuery(p)
    );
  }
  if (!window.__EO_LANG_OK__) { window.__EO_LANG_OK__ = {}; }
})();
"""

_WS_PAGE_HOOK = r"""
(() => {
  try {
    if (window.__WS_HOOK_INSTALLED__) return;
    window.__WS_HOOK_INSTALLED__ = true;
    window.__WS_FRAMES__ = [];
    const TD = (typeof TextDecoder !== 'undefined') ? new TextDecoder() : null;
    const OrigWS = window.WebSocket;
    function Wrap(url, protocols) {
      const ws = protocols ? new OrigWS(url, protocols) : new OrigWS(url);
      ws.addEventListener("message", (ev) => {
        try {
          if (typeof ev.data === "string") {
            window.__WS_FRAMES__.push({dir: "in", url: url || "", text: ev.data});
          } else if (ev.data && ev.data.text) {
            ev.data.text().then(t => { window.__WS_FRAMES__.push({dir:"in",url:url||"",text:t}); }).catch(()=>{});
          } else if (ev.data && ev.data.arrayBuffer) {
            ev.data.arrayBuffer().then(buf => {
              try { const t = TD ? TD.decode(new Uint8Array(buf)) : ''; window.__WS_FRAMES__.push({dir:"in",url:url||"",text:t}); } catch(e) {}
            }).catch(()=>{});
          }
        } catch (e) {}
      });
      return ws;
    }
    Wrap.prototype = OrigWS.prototype;
    ['OPEN','CLOSED','CLOSING','CONNECTING'].forEach(k => { Wrap[k] = OrigWS[k]; });
    Object.defineProperty(window, 'WebSocket', { get: () => Wrap, set: () => {}, configurable: false });
  } catch (e) {}
})();
"""

def _maybe_b64_json(text: str) -> Optional[dict]:
    if not isinstance(text, str):
        return None
    if not re.fullmatch(r'[A-Za-z0-9+/= \r\n\t]+', text.strip()):
        return None
    try:
        raw = base64.b64decode(text, validate=False)
        s = raw.decode("utf-8", "ignore")
        return json.loads(s)
    except Exception:
        return None

def _json_find_token(obj) -> Optional[str]:
    try:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "token" and isinstance(v, str) and re.fullmatch(TOKEN_32HEX_RE, v):
                    return v
                r = _json_find_token(v)
                if r:
                    return r
        elif isinstance(obj, list):
            for it in obj:
                r = _json_find_token(it)
                if r:
                    return r
    except Exception:
        pass
    return None

def _extract_token_any(payload: str) -> Optional[str]:
    if not payload:
        return None
    try:
        o = json.loads(payload)
        t = _json_find_token(o)
        if t:
            return t
    except Exception:
        pass
    o2 = _maybe_b64_json(payload)
    if o2:
        t = _json_find_token(o2)
        if t:
            return t
    return None

async def seed_language_cookies_for_all(context: BrowserContext) -> None:
    try:
        expires = int(time.time()) + 3600 * 24 * 365
        bases = [".expertoption.com", "expertoption.com", "app.expertoption.com", "www.expertoption.com"]
        cookies = []
        for dom in bases:
            cookies += [
                {"name": "i18next", "value": "en", "domain": dom, "path": "/", "httpOnly": False, "secure": True, "sameSite": "Lax", "expires": expires},
                {"name": "lang", "value": "en", "domain": dom, "path": "/", "httpOnly": False, "secure": True, "sameSite": "Lax", "expires": expires},
            ]
        await context.add_cookies(cookies)
        logger.info("Language cookies pre-seeded across EO domains (i18next=en, lang=en)")
    except Exception as e:
        logger.warning(f"Failed to pre-seed language cookies: {e}")

async def _handle_language_modal_once(page: Page) -> None:
    try:
        host = page.url.split('/')[2] if '://' in page.url else 'unknown'
    except Exception:
        host = 'unknown'
    already = await page.evaluate("(h)=> (window.__EO_LANG_OK__ && window.__EO_LANG_OK__[h]) || false", host)
    if already:
        return
    try:
        await page.wait_for_selector("div.css-b0egdr", timeout=4000)
    except PlaywrightTimeoutError:
        return
    try:
        tile = page.locator("text=English").first
        if await tile.count() > 0 and await tile.is_visible():
            await tile.click(timeout=2000)
            logger.info(f"[{host}] Language 'English' tile clicked (by text)")
    except Exception:
        try:
            await page.locator("div.css-hkiiff").first.click(timeout=2000)
            logger.info(f"[{host}] Language tile clicked (.css-hkiiff)")
        except Exception:
            pass
    for sel in ["button.full-width.css-mlz3dn", 'button:has-text("Confirm")', 'button:has-text("تأكيد")']:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.click(timeout=2000)
                logger.info(f"[{host}] Confirm clicked")
                break
        except Exception:
            continue
    try:
        await page.wait_for_selector("div.css-b0egdr", state="detached", timeout=6000)
    except PlaywrightTimeoutError:
        pass
    await page.evaluate("(h)=>{ if(!window.__EO_LANG_OK__) window.__EO_LANG_OK__={}; window.__EO_LANG_OK__[h]=true; }", host)

async def _set_value_strict(page: Page, handle, value: str) -> bool:
    try:
        await handle.fill(value, timeout=3000)
    except Exception:
        try:
            await handle.click(timeout=1000)
            await page.keyboard.type(value, delay=10)
        except Exception:
            await page.evaluate("""(el,val)=>{
                const d = Object.getOwnPropertyDescriptor(el.__proto__,'value')
                          || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');
                d.set.call(el,val);
                el.dispatchEvent(new Event('input',{bubbles:true}));
                el.dispatchEvent(new Event('change',{bubbles:true}));
            }""", handle, value)
    await page.evaluate("""(el)=>{
        el.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true}));
        el.dispatchEvent(new Event('blur',{bubbles:true}));
    }""", handle)
    try:
        cur = await page.evaluate("(el)=>el && el.value || ''", handle)
        return cur == value
    except Exception:
        return True

async def _fill_and_submit(page: Page, email: str, password: str) -> Tuple[bool, str]:
    pwd = page.locator("#password, input[type='password'], input[name='password']").first
    if await pwd.count() == 0:
        return False, "Password field not found"
    pwd_h = await pwd.element_handle()
    if not pwd_h:
        return False, "Password handle missing"
    form_h = await page.evaluate_handle("(el)=>el.closest('form')", pwd_h)
    form = form_h.as_element() if form_h else None
    if form:
        email_h = await form.evaluate_handle("""(f)=>{
            return f.querySelector('#login, input[type=email], input[name=email], input[name=login], input[autocomplete=username]');
        }""")
        email_el = email_h.as_element() if email_h else None
    else:
        email_el = None
    if not email_el:
        tmp = page.locator("#login, input[type='email'], input[name='email'], input[name='login']").first
        email_el = await tmp.element_handle()
    if not email_el:
        return False, "Email field not found"
    if not await _set_value_strict(page, email_el, email):
        return False, "Failed email fill"
    if not await _set_value_strict(page, pwd_h, password):
        return False, "Failed password fill"
    clicked = False
    if form:
        btn_h = await form.evaluate_handle("""(f)=>{
            const cs = Array.from(f.querySelectorAll('button, input[type=submit]'));
            let prefer = cs.find(el => (el.matches('button[type=submit],input[type=submit]') && !el.disabled));
            if (prefer) return prefer;
            const labels = ['login','sign in','الدخول','تسجيل الدخول'];
            const norm = (s)=> (s||'').trim().toLowerCase();
            for (const el of cs) {
                const t = norm(el.innerText || el.textContent);
                if (labels.some(l => t.includes(l))) return el;
            }
            return cs.find(el => el.type === 'submit') || cs[0] || null;
        }""")
        btn = btn_h.as_element() if btn_h else None
        if btn:
            try:
                await btn.click(timeout=1500)
                clicked = True
            except Exception:
                try:
                    await btn.click(timeout=1500, force=True)
                    clicked = True
                except Exception:
                    try:
                        await page.evaluate("(b)=>b && b.click()", btn)
                        clicked = True
                    except Exception:
                        clicked = False
    if not clicked:
        try:
            await pwd.press("Enter")
            clicked = True
        except Exception:
            pass
    if not clicked and form:
        try:
            ok = await page.evaluate("""(f)=>{
                if (!f) return false;
                if (typeof f.requestSubmit==='function'){ f.requestSubmit(); return true; }
                f.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
                try { f.submit(); } catch(_){}
                return true;
            }""", form)
            clicked = bool(ok)
        except Exception:
            pass
    return (True, "") if clicked else (False, "Failed to trigger submit")

async def _attach_context_ws(context: BrowserContext, sink: Dict) -> None:
    def on_ws(ws: WebSocket):
        def on_frame_recv(data):
            t = _extract_token_any_from_ws(ws.url, data)
            if t and not sink.get("token"):
                sink["token"] = t
                logger.info(f"Token captured from WebSocket frame: {t[:12]}...")
        def on_frame_sent(data):
            t = _extract_token_any_from_ws(ws.url, data)
            if t and not sink.get("token"):
                sink["token"] = t
                logger.info(f"Token captured from WebSocket frame: {t[:12]}...")
        try:
            ws.on("framereceived", on_frame_recv)
            ws.on("framesent", on_frame_sent)
        except Exception:
            pass
    context.on("websocket", on_ws)

async def _attach_cdp_ws(page: Page, sink: Dict) -> None:
    client = await page.context.new_cdp_session(page)
    await client.send("Network.enable")
    ws_urls: Dict[str, str] = {}
    def ws_created(params):
        try:
            rid = params.get("requestId")
            url = params.get("url", "")
            ws_urls[rid] = url
        except Exception:
            pass
    def ws_frame_recv(params):
        try:
            rid = params.get("requestId")
            url = ws_urls.get(rid, "")
            payload = (params.get("response") or {}).get("payloadData", "")
            t = _extract_token_any_from_ws(url, payload)
            if t and not sink.get("token"):
                sink["token"] = t
                logger.info(f"Token captured from CDP frame: {t[:12]}...")
        except Exception:
            pass
    def ws_frame_sent(params):
        try:
            rid = params.get("requestId")
            url = ws_urls.get(rid, "")
            payload = (params.get("response") or {}).get("payloadData", "")
            t = _extract_token_any_from_ws(url, payload)
            if t and not sink.get("token"):
                sink["token"] = t
                logger.info(f"Token captured from CDP frame: {t[:12]}...")
        except Exception:
            pass
    client.on("Network.webSocketCreated", ws_created)
    client.on("Network.webSocketFrameReceived", ws_frame_recv)
    client.on("Network.webSocketFrameSent", ws_frame_sent)

async def _scan_injected_ws(page: Page) -> Optional[str]:
    try:
        frames = await page.evaluate("window.__WS_FRAMES__ || []")
        if not isinstance(frames, list):
            return None
        for fr in frames:
            url = (fr or {}).get("url", "")
            txt = (fr or {}).get("text", "")
            t = _extract_token_any_from_ws(url, txt)
            if t:
                logger.info(f"Token captured from injected WS: {t[:12]}...")
                return t
    except Exception:
        return None
    return None

def _extract_token_any_from_ws(url: str, data) -> Optional[str]:
    try:
        if url and WS_URL_HINT not in url:
            return None
    except Exception:
        pass
    try:
        s = data.decode("utf-8", "ignore") if isinstance(data, (bytes, bytearray)) else str(data or "")
    except Exception:
        return None
    return _extract_token_any(s)

async def _make_client_with_region(token: str, is_demo: bool, region_name: str, ws_url: str):
    from .client import AsyncExpertOptionClient
    try:
        client = AsyncExpertOptionClient(
            token=token,
            is_demo=is_demo,
            region=region_name,
            persistent_connection=False,
        )
        return client
    except TypeError as e:
        logger.warning(f"Failed to initialize client with region {region_name}: {e}")
        return AsyncExpertOptionClient(token=token, is_demo=is_demo, persistent_connection=False)

async def validate_token(token: str, is_demo: bool = True) -> bool:
    if not token or not re.fullmatch(TOKEN_32HEX_RE, token):
        logger.error("Invalid token format")
        return False
    for name, url in REGIONS.get_all_regions().items():
        try:
            client = await _make_client_with_region(token, is_demo, name, url)
            ok = await client.connect()
            try:
                await client.disconnect()
            except Exception:
                pass
            if ok:
                logger.info(f"Token validated via region {name}")
                return True
        except Exception as e:
            logger.warning(f"Token validation failed for region {name}: {e}")
    logger.error("Token validation failed for all regions")
    return False

async def get_token(email: str | None = None, password: str | None = None, *, is_demo: bool = True, headless: bool = True, total_timeout_ms: int = 120_000, save_creds_to_config: bool = True) -> Tuple[bool, Dict]:
    sess = _load_session()
    saved_token = (sess.get("token") or "").strip()
    saved_is_demo = bool(sess.get("is_demo", 1))
    if saved_token and re.fullmatch(TOKEN_32HEX_RE, saved_token):
        try:
            ok = await validate_token(saved_token, is_demo=saved_is_demo)
        except Exception as e:
            logger.warning(f"validate_token raised: {e}")
            ok = False
        if ok:
            logger.info("Using token from session.json (validated).")
            payload = {
                "token": saved_token,
                "is_demo": 1 if saved_is_demo else 0,
                "ts": int(sess.get("ts") or time.time()),
            }
            save_session(payload)
            return True, payload
        else:
            logger.warning("Saved token invalid/expired; clearing session.json and continuing to Playwright login.")
            _clear_session_file()
    if not email or not password:
        cfg = load_config()
        email = email or cfg.get("email")
        password = password or cfg.get("password") or cfg.get("password_plain") or cfg.get("password_enc")
        if not email or not password:
            logger.error("Email/password not found in config.json or provided")
            raise RuntimeError("Email/password not found in config.json. Provide them to get_token() or set config.json")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
                "--no-first-run",
                "--start-maximized",
                "--incognito",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Riyadh",
            java_script_enabled=True,
            extra_http_headers={"Accept-Language": "en-US,en;q=0.8,ar;q=0.3"},
        )
        await context.add_init_script(_STEALTH_JS)
        await context.add_init_script(_WS_PAGE_HOOK)
        await seed_language_cookies_for_all(context)
        sink: Dict = {}
        await _attach_context_ws(context, sink)
        page = await context.new_page()
        await _attach_cdp_ws(page, sink)
        async def on_new_page(p: Page):
            try:
                await _attach_cdp_ws(p, sink)
            except Exception:
                pass
        context.on("page", lambda p: asyncio.create_task(on_new_page(p)))
        try:
            await page.goto(EO_LOGIN, wait_until="domcontentloaded", timeout=60_000)
            await _handle_language_modal_once(page)
            if "app.expertoption.com" in page.url:
                await page.goto(EO_LOGIN, wait_until="domcontentloaded", timeout=60_000)
                await _handle_language_modal_once(page)
            email_input = page.locator(
                '#login, input[type="email"], input[name="email"], input[name="login"], input[autocomplete="username"]'
            ).first
            pass_input = page.locator(
                '#password, input[type="password"], input[name="password"], input[autocomplete="current-password"]'
            ).first
            if await email_input.count() > 0:
                await _set_value_strict(page, await email_input.element_handle(), email)
            if await pass_input.count() > 0:
                await _set_value_strict(page, await pass_input.element_handle(), password)
            ok_submit, err = await _fill_and_submit(page, email, password)
            if not ok_submit:
                logger.warning(f"Submit failed: {err}")
            await page.wait_for_timeout(1000)
            try:
                await page.goto(EO_APP, wait_until="domcontentloaded", timeout=60_000)
            except PlaywrightTimeoutError:
                logger.warning("Timeout navigating to app.expertoption.com")
            token: Optional[str] = None
            deadline = time.time() + total_timeout_ms / 1000.0
            while time.time() < deadline and not token:
                token = sink.get("token") or token
                if not token:
                    token = await _scan_injected_ws(page)
                if token and not re.fullmatch(TOKEN_32HEX_RE, token):
                    logger.warning(f"Ignoring non-32hex token candidate: {token[:12]}...")
                    token = None
                if token:
                    break
                await page.wait_for_timeout(250)
            if token:
                payload = {"token": token, "is_demo": 1 if is_demo else 0, "ts": int(time.time())}
                save_session(payload)
                logger.info(f"Session saved with token: {token[:12]}...")
            await context.close()
            await browser.close()
            if not token:
                logger.error("Failed to obtain TOKEN via WS")
                await error_monitor.record_error(
                    error_type="ws_login_failed",
                    severity=ErrorSeverity.CRITICAL,
                    category=ErrorCategory.AUTHENTICATION,
                    message="Failed to obtain TOKEN via WS",
                )
                return False, {}
            try:
                if not await validate_token(token, is_demo=is_demo):
                    logger.error("Token failed live validation")
                    await error_monitor.record_error(
                        error_type="token_validation_failed",
                        severity=ErrorSeverity.CRITICAL,
                        category=ErrorCategory.AUTHENTICATION,
                        message="Token failed live validation",
                    )
                    return False, payload
            except Exception as e:
                logger.warning(f"Validation error: {e}")
            if save_creds_to_config:
                cfg = load_config()
                cfg.update({"email": email, "password": password})
                save_config(cfg)
            return True, payload
        except Exception as e:
            logger.error(f"Playwright login error: {e}")
            await error_monitor.record_error(
                error_type="ws_login_failed",
                severity=ErrorSeverity.CRITICAL,
                category=ErrorCategory.AUTHENTICATION,
                message=f"WS login failed: {e}",
            )
            try:
                await context.close()
                await browser.close()
            except Exception:
                pass
            return False, {}
