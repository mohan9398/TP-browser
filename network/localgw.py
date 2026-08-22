import threading
import urllib.request
import urllib.error
import urllib.parse
import socketserver
import gzip
import zlib
import re
import html
from http.server import BaseHTTPRequestHandler

from secure_browser.core.config import PROXY_TARGET_ORIGINS
from secure_browser.core.logger import get_logger

log = get_logger(__name__)

PROXY_HOST = "127.0.0.1"

# netloc (host[:port]) -> proxy origin (http://127.0.0.1:<port>)
_routes = {}

TEXTUAL_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "text/css",
    "text/javascript",
    "application/javascript",
    "application/x-javascript",
    "application/json",
    "application/xml",
    "text/xml",
)


class TargetContext:
    """Everything one proxy instance needs to forward to a single upstream.

    Each reverse-proxy target gets its own TargetContext and its own localhost
    port, so the header/cookie/URL-rewriting logic stays as simple as the old
    single-target proxy — it just reads its target from here instead of module
    globals.
    """

    def __init__(self, target_origin: str):
        parsed = urllib.parse.urlsplit(target_origin)
        self.target_origin = target_origin.rstrip("/")
        self.target_scheme = parsed.scheme or "http"
        self.target_host = parsed.hostname or ""
        # parsed.port raises ValueError on a malformed netloc (e.g. a missing
        # comma glued two origins together). Treat that as "no host" so
        # start_proxy skips this entry instead of crashing the whole app.
        try:
            self.target_port = parsed.port
        except ValueError:
            self.target_port = None
            self.target_host = ""
        self.target_netloc = parsed.netloc  # host[:port], no scheme
        # Filled in once the server is bound to a port.
        self.proxy_port = 0
        self.proxy_origin = ""


def get_proxy_routes() -> dict:
    """Returns {target_netloc: proxy_origin} for every started proxy."""
    return dict(_routes)


def get_proxy_origin() -> str:
    """Backwards-compatible: the proxy origin for the FIRST target, or ""."""
    if _routes:
        return next(iter(_routes.values()))
    return ""


def is_textual_content_type(content_type: str) -> bool:
    ct = (content_type or "").lower()
    return any(x in ct for x in TEXTUAL_CONTENT_TYPES)


def decode_bytes(raw: bytes, content_type: str) -> tuple[str, str]:
    ct = content_type or ""
    m = re.search(r"charset=([^\s;]+)", ct, flags=re.I)
    candidates = []
    if m:
        candidates.append(m.group(1).strip("\"'"))
    candidates.extend(["utf-8", "latin-1"])

    for enc in candidates:
        try:
            return raw.decode(enc), enc
        except Exception:
            continue

    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


class ProxyHandler(BaseHTTPRequestHandler):
    # ── Per-request access to this proxy's target ───────────────────────────
    @property
    def ctx(self) -> TargetContext:
        return self.server.ctx

    def log_message(self, fmt, *args):
        pass  # Suppress default logging

    # ── Rewriting helpers (target-aware via self.ctx) ───────────────────────
    def rewrite_text_payload(self, text: str, content_type: str) -> tuple[str, int]:
        ctx = self.ctx
        count = 0
        if not ctx.proxy_origin:
            return text, 0

        proxy_origin = ctx.proxy_origin
        proxy_netloc = f"{PROXY_HOST}:{ctx.proxy_port}"
        target_origin = ctx.target_origin
        target_netloc = ctx.target_netloc

        # direct origin replacements
        if target_origin in text:
            n = text.count(target_origin)
            text = text.replace(target_origin, proxy_origin)
            count += n

        # escaped/slashed variants sometimes appear in JSON/JS
        escaped_target = target_origin.replace("/", r"\/")
        escaped_proxy = proxy_origin.replace("/", r"\/")
        if escaped_target in text:
            n = text.count(escaped_target)
            text = text.replace(escaped_target, escaped_proxy)
            count += n

        # scheme-relative //host[:port]
        scheme_relative_target = f"//{target_netloc}"
        scheme_relative_proxy = f"//{proxy_netloc}"
        if scheme_relative_target in text:
            n = text.count(scheme_relative_target)
            text = text.replace(scheme_relative_target, scheme_relative_proxy)
            count += n

        # HTML entity escaped target can show up
        escaped_html_target = html.escape(target_origin)
        escaped_html_proxy = html.escape(proxy_origin)
        if escaped_html_target in text:
            n = text.count(escaped_html_target)
            text = text.replace(escaped_html_target, escaped_html_proxy)
            count += n

        return text, count

    def rewrite_location(self, location: str) -> tuple[str, bool]:
        ctx = self.ctx
        if not location or not ctx.proxy_origin:
            return location, False

        if location.startswith(ctx.target_origin):
            rewritten = ctx.proxy_origin + location[len(ctx.target_origin):]
            return rewritten, True

        if location.startswith("/"):
            return ctx.proxy_origin + location, True

        return location, False

    def rewrite_set_cookie(self, cookie_value: str) -> tuple[str, bool]:
        original = cookie_value
        rewritten = cookie_value

        # Remove Domain=... entirely so cookie becomes host-only for 127.0.0.1
        rewritten = re.sub(r";\s*Domain=[^;]+", "", rewritten, flags=re.I)
        # Strip Secure attribute if present to avoid dropping it on http localhost
        rewritten = re.sub(r";\s*Secure\b", "", rewritten, flags=re.I)

        return rewritten, (rewritten != original)

    def _send_error_page(self, code: int, title: str, message: str):
        """Send a calm, branded HTML error page instead of a raw 502.

        Seeing a bare server error mid-exam looks like a crash; this explains
        what happened and tells the student what to do.
        """
        html_page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html,body{{height:100%;margin:0}}
  body{{display:flex;align-items:center;justify-content:center;
    font-family:'Segoe UI',system-ui,sans-serif;background:#f5f0eb;color:#3c3631}}
  .card{{max-width:520px;text-align:center;padding:48px 40px;background:#fff;
    border:1px solid #e6dace;border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.06)}}
  .icon{{font-size:56px;margin-bottom:12px}}
  h1{{font-size:22px;margin:0 0 10px;color:#292524}}
  p{{font-size:15px;line-height:1.6;color:#6b7280;margin:0 0 24px}}
  button{{background:#292524;color:#fff;border:none;border-radius:8px;
    padding:12px 28px;font-size:15px;font-weight:600;cursor:pointer}}
  button:hover{{background:#44403c}}
  .hint{{margin-top:18px;font-size:13px;color:#a89f91}}
</style></head>
<body><div class="card">
  <div class="icon">📡</div>
  <h1>{title}</h1>
  <p>{message}</p>
  <button onclick="location.reload()">↻ Try Again</button>
  <div class="hint">If this keeps happening, use the <b>Network</b> button
  in the toolbar to check your Wi-Fi connection.</div>
</div></body></html>"""
        raw = html_page.encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
        except Exception:
            pass

    def _decompress(self, raw: bytes, encoding: str) -> bytes:
        enc = (encoding or "").lower().strip()
        try:
            if enc == "gzip":
                return gzip.decompress(raw)
            elif enc in ("deflate", "zlib"):
                return zlib.decompress(raw)
            elif enc == "br":
                try:
                    import brotli
                    return brotli.decompress(raw)
                except ImportError:
                    pass
        except Exception as e:
            pass
        return raw

    def _build_target_url(self) -> str:
        ctx = self.ctx
        if self.path.startswith("http://") or self.path.startswith("https://"):
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.hostname == PROXY_HOST and parsed.port == ctx.proxy_port:
                rebuilt = urllib.parse.urlunsplit((
                    ctx.target_scheme,
                    ctx.target_netloc,
                    parsed.path,
                    parsed.query,
                    parsed.fragment,
                ))
                return rebuilt
            return self.path
        return f"{ctx.target_origin}{self.path}"

    class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
        def http_error_302(self, req, fp, code, msg, headers):
            return fp
        http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    def _forward(self, body=None):
        ctx = self.ctx
        target_url = self._build_target_url()
        response_started = False

        headers = {"Accept-Encoding": "identity"}
        for k, v in self.headers.items():
            kl = k.lower()
            if kl == "host":
                headers["Host"] = ctx.target_netloc
            elif kl not in ("content-length", "transfer-encoding", "connection", "accept-encoding", "origin", "referer"):
                headers[k] = v
            elif kl == "origin":
                headers[k] = ctx.target_origin
            elif kl == "referer":
                headers[k] = v.replace(ctx.proxy_origin, ctx.target_origin)

        try:
            req = urllib.request.Request(target_url, data=body, headers=headers, method=self.command)
            # Explicitly bypass any system/OS proxy (ProxyHandler({})) — the
            # target is always our known internal exam server, and honoring
            # a configured system proxy here can make it unreachable even
            # though a normal browser (which bypasses proxies for local/
            # intranet addresses) connects to it fine.
            opener = urllib.request.build_opener(
                self.NoRedirectHandler(), urllib.request.ProxyHandler({})
            )
            with opener.open(req, timeout=30) as resp:
                encoding = resp.headers.get("Content-Encoding", "")
                content_type = resp.headers.get("Content-Type", "")

                # If it's a textual type, we must buffer and rewrite
                # If it's binary, we stream it directly
                is_text = is_textual_content_type(content_type)

                # Send response code
                self.send_response(resp.status)
                response_started = True

                if is_text:
                    raw = resp.read() # Buffer full text

                    if encoding and encoding.lower() not in ("identity", ""):
                        raw = self._decompress(raw, encoding)

                    text, encoding_used = decode_bytes(raw, content_type)
                    rewritten_text, replacements = self.rewrite_text_payload(text, content_type)

                    if replacements:
                        raw = rewritten_text.encode(encoding_used, errors="replace")
                    else:
                        raw = text.encode(encoding_used, errors="replace")

                    # Write modified headers block
                    for k, v in resp.getheaders():
                        kl = k.lower()
                        if kl in ("transfer-encoding", "content-encoding", "connection", "keep-alive"):
                            continue
                        if kl == "location":
                            new_v, changed = self.rewrite_location(v)
                            self.send_header(k, new_v)
                            continue
                        if kl == "set-cookie":
                            new_v, changed = self.rewrite_set_cookie(v)
                            self.send_header(k, new_v)
                            continue
                        if kl == "content-length":
                            continue # Overridden below
                        self.send_header(k, v)

                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()

                    try:
                        self.wfile.write(raw)
                    except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                        pass

                else:
                    # BINARY STREAMING PATH - Greatly improves performance for images, videos etc
                    # No buffering into memory, chunk directly to browser
                    # Send headers exactly as received (except connection/chunking)
                    for k, v in resp.getheaders():
                        kl = k.lower()
                        if kl in ("transfer-encoding", "connection", "keep-alive"):
                            continue
                        self.send_header(k, v)

                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()

                    try:
                        while True:
                            chunk = resp.read(8192) # 8KB chunks
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                    except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                        pass

        except urllib.error.HTTPError as e:
            response_started = True
            body_err = e.read()
            content_type = e.headers.get("Content-Type", "")

            if is_textual_content_type(content_type):
                try:
                    text, enc = decode_bytes(body_err, content_type)
                    text2, replacements = self.rewrite_text_payload(text, content_type)
                    if replacements:
                        body_err = text2.encode(enc, errors="replace")
                except Exception as ex:
                    pass

            self.send_response(e.code)
            for k, v in e.headers.items():
                kl = k.lower()
                if kl in ("transfer-encoding", "content-encoding", "connection", "content-length"):
                    continue
                if kl == "location":
                    new_v, changed = self.rewrite_location(v)
                    self.send_header(k, new_v)
                    continue
                if kl == "set-cookie":
                    new_v, changed = self.rewrite_set_cookie(v)
                    self.send_header(k, new_v)
                    continue
                self.send_header(k, v)

            self.send_header("Content-Length", str(len(body_err)))
            self.end_headers()
            try:
                self.wfile.write(body_err)
            except Exception:
                pass

        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass # Browser aborted
        except Exception as e:
            log.warning("Proxy could not reach exam server (%s): %s",
                        target_url, e)
            if response_started:
                # Headers (and maybe partial body) already went out — sending
                # another status line now would produce a malformed response
                # that Chromium reports as a raw connection failure (showing
                # our app's generic offline overlay) instead of this friendly
                # page. Just let the connection close.
                return
            self._send_error_page(
                502,
                "Can't reach the exam server",
                "The browser could not connect to the exam server. This is "
                "usually a Wi-Fi or network problem, not an error with your "
                "exam. Please check your connection and try again.",
            )

    def do_GET(self): self._forward()
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self._forward(self.rfile.read(n) if n else None)
    def do_PUT(self):
        n = int(self.headers.get("Content-Length", 0))
        self._forward(self.rfile.read(n) if n else None)
    def do_DELETE(self): self._forward()
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()


class ThreadedProxy(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_cls, ctx: TargetContext):
        self.ctx = ctx
        super().__init__(server_address, handler_cls)


def _start_one(target_origin: str) -> TargetContext | None:
    """Start a single proxy bound to a free localhost port for one target."""
    ctx = TargetContext(target_origin)
    if not ctx.target_host:
        log.warning("Skipping proxy target with no host: %r", target_origin)
        return None

    ready = threading.Event()
    holder = {}

    def _run():
        try:
            srv = ThreadedProxy((PROXY_HOST, 0), ProxyHandler, ctx)
            ctx.proxy_port = srv.server_address[1]
            ctx.proxy_origin = f"http://{PROXY_HOST}:{ctx.proxy_port}"
            holder["ok"] = True
            ready.set()
            srv.serve_forever()
        except Exception:
            log.exception("Proxy failed to start for %s", target_origin)
            ready.set()

    threading.Thread(
        target=_run, daemon=True, name=f"Proxy-{ctx.target_host}"
    ).start()
    ready.wait(timeout=5)
    return ctx if holder.get("ok") else None


def start_proxy(target_origins=None) -> dict:
    """
    Start one reverse proxy per target origin.

    Returns {target_netloc: proxy_origin}, e.g.
        {"172.168.11.105": "http://127.0.0.1:51234",
         "172.168.15.213": "http://127.0.0.1:51235"}

    The mapping is also stored globally (see get_proxy_routes()).
    """
    global _routes
    if target_origins is None:
        target_origins = PROXY_TARGET_ORIGINS

    routes = {}
    for origin in target_origins:
        # One bad entry must never stop the app from opening — skip and continue.
        try:
            ctx = _start_one(origin)
        except Exception:
            log.exception("Skipping bad proxy target: %r", origin)
            continue
        if ctx:
            routes[ctx.target_netloc] = ctx.proxy_origin
            log.info("Proxy up: %s  ->  %s", ctx.target_netloc, ctx.proxy_origin)

    _routes = routes
    return routes
