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

from secure_browser.core.config import TARGET_ORIGIN, TARGET_NETLOC

PROXY_HOST = "127.0.0.1"
_proxy_port = 0
_proxy_origin = ""

# Extracted from TARGET_ORIGIN
try:
    TARGET_PARSED = urllib.parse.urlsplit(TARGET_ORIGIN)
    TARGET_SCHEME = TARGET_PARSED.scheme
    TARGET_HOST = TARGET_PARSED.hostname or ""
    TARGET_PORT = TARGET_PARSED.port
except Exception as e:
    TARGET_SCHEME = "http"

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

def get_proxy_origin():
    """Returns the dynamically assigned proxy origin."""
    return _proxy_origin

def get_proxy_port():
    """Returns the dynamically assigned proxy port."""
    return _proxy_port

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

def rewrite_text_payload(text: str, content_type: str) -> tuple[str, int]:
    count = 0
    if not _proxy_origin:
        return text, 0
        
    proxy_origin = _proxy_origin
    proxy_netloc = f"{PROXY_HOST}:{_proxy_port}"
    
    # direct origin replacements
    if TARGET_ORIGIN in text:
        n = text.count(TARGET_ORIGIN)
        text = text.replace(TARGET_ORIGIN, proxy_origin)
        count += n

    # escaped/slashed variants sometimes appear in JSON/JS
    escaped_target = TARGET_ORIGIN.replace("/", r"\/")
    escaped_proxy = proxy_origin.replace("/", r"\/")
    if escaped_target in text:
        n = text.count(escaped_target)
        text = text.replace(escaped_target, escaped_proxy)
        count += n

    # scheme-relative //host[:port]
    scheme_relative_target = f"//{TARGET_NETLOC}"
    scheme_relative_proxy = f"//{proxy_netloc}"
    if scheme_relative_target in text:
        n = text.count(scheme_relative_target)
        text = text.replace(scheme_relative_target, scheme_relative_proxy)
        count += n

    # HTML entity escaped target can show up
    escaped_html_target = html.escape(TARGET_ORIGIN)
    escaped_html_proxy = html.escape(proxy_origin)
    if escaped_html_target in text:
        n = text.count(escaped_html_target)
        text = text.replace(escaped_html_target, escaped_html_proxy)
        count += n

    return text, count

def rewrite_location(location: str) -> tuple[str, bool]:
    if not location or not _proxy_origin:
        return location, False

    if location.startswith(TARGET_ORIGIN):
        rewritten = _proxy_origin + location[len(TARGET_ORIGIN):]
        return rewritten, True

    if location.startswith("/"):
        return _proxy_origin + location, True

    return location, False

def rewrite_set_cookie(cookie_value: str) -> tuple[str, bool]:
    original = cookie_value
    rewritten = cookie_value

    # Remove Domain=... entirely so cookie becomes host-only for 127.0.0.1
    rewritten = re.sub(r";\s*Domain=[^;]+", "", rewritten, flags=re.I)
    # Strip Secure attribute if present to avoid dropping it on http localhost
    rewritten = re.sub(r";\s*Secure\b", "", rewritten, flags=re.I)

    return rewritten, (rewritten != original)

class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass # Suppress default logging

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
        if self.path.startswith("http://") or self.path.startswith("https://"):
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.hostname == PROXY_HOST and parsed.port == _proxy_port:
                rebuilt = urllib.parse.urlunsplit((
                    TARGET_SCHEME,
                    TARGET_NETLOC,
                    parsed.path,
                    parsed.query,
                    parsed.fragment,
                ))
                return rebuilt
            return self.path
        return f"{TARGET_ORIGIN}{self.path}"

    class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
        def http_error_302(self, req, fp, code, msg, headers):
            return fp
        http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    def _forward(self, body=None):
        target_url = self._build_target_url()

        headers = {"Accept-Encoding": "identity"}
        for k, v in self.headers.items():
            kl = k.lower()
            if kl == "host":
                headers["Host"] = TARGET_NETLOC
            elif kl not in ("content-length", "transfer-encoding", "connection", "accept-encoding", "origin", "referer"):
                headers[k] = v
            elif kl == "origin":
                headers[k] = TARGET_ORIGIN
            elif kl == "referer":
                headers[k] = v.replace(_proxy_origin, TARGET_ORIGIN)

        try:
            req = urllib.request.Request(target_url, data=body, headers=headers, method=self.command)
            opener = urllib.request.build_opener(self.NoRedirectHandler())
            with opener.open(req, timeout=30) as resp:
                encoding = resp.headers.get("Content-Encoding", "")
                content_type = resp.headers.get("Content-Type", "")

                # If it's a textual type, we must buffer and rewrite
                # If it's binary, we stream it directly
                is_text = is_textual_content_type(content_type)
                
                # Send response code
                self.send_response(resp.status)

                if is_text:
                    raw = resp.read() # Buffer full text
                    
                    if encoding and encoding.lower() not in ("identity", ""):
                        raw = self._decompress(raw, encoding)

                    text, encoding_used = decode_bytes(raw, content_type)
                    rewritten_text, replacements = rewrite_text_payload(text, content_type)
                    
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
                            new_v, changed = rewrite_location(v)
                            self.send_header(k, new_v)
                            continue
                        if kl == "set-cookie":
                            new_v, changed = rewrite_set_cookie(v)
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
            body_err = e.read()
            content_type = e.headers.get("Content-Type", "")

            if is_textual_content_type(content_type):
                try:
                    text, enc = decode_bytes(body_err, content_type)
                    text2, replacements = rewrite_text_payload(text, content_type)
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
                    new_v, changed = rewrite_location(v)
                    self.send_header(k, new_v)
                    continue
                if kl == "set-cookie":
                    new_v, changed = rewrite_set_cookie(v)
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
            try:
                self.send_error(502, str(e))
            except Exception:
                pass

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


def start_proxy() -> int:
    """
    Starts the proxy on a dynamic port and returns the port bound.
    """
    global _proxy_port, _proxy_origin
    ready = threading.Event()
    bound_port_container = []

    def _run():
        try:
            # Bind to port 0 to let OS pick a free port
            srv = ThreadedProxy((PROXY_HOST, 0), ProxyHandler)
            allocated_port = srv.server_address[1]
            bound_port_container.append(allocated_port)
            ready.set()
            srv.serve_forever()
        except Exception as e:
            ready.set()

    t = threading.Thread(target=_run, daemon=True, name="ProxyServer")
    t.start()
    ready.wait(timeout=5)
    
    if bound_port_container:
        _proxy_port = bound_port_container[0]
        _proxy_origin = f"http://{PROXY_HOST}:{_proxy_port}"
        return _proxy_port
    
    return 0
