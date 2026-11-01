#!/usr/bin/env python3
"""Zability Craft Bridge - lets Intelligent WebUI create real Office files with the
Craft CLIs and open them in the streamed Craft desktop. Stdlib only. LAN/internal only.

Endpoints (all but /health need header X-Craft-Token):
  GET  /health                -> {ok, apps}
  POST /make  {kind, format, name, open, ...content}  -> {name, mime, size, b64}
  POST /open  {name, b64, app?}                         -> {opened, app, path}
"""
import base64, hmac, json, os, re, shutil, subprocess, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOME = os.environ.get("HOME", "/config")
INBOX = os.path.join(HOME, "Inbox")
APPS_DIR = os.path.join(HOME, "apps")
TOKEN_FILE = os.path.join(HOME, ".craft-bridge-token")
PORT = int(os.environ.get("CRAFT_BRIDGE_PORT", "8790"))
MAX_BODY = 60 * 1024 * 1024
LOCK = threading.Lock()

APPS = ["wordcraft", "gridcraft", "deckcraft", "cadcraft", "soundcraft", "photocraft", "vectorcraft",
        "filmcraft", "lightcraft", "pdfcraft", "effectcraft", "designcraft", "figcraft", "artcraft-launcher"]
EXT_APP = {
    "docx": "wordcraft", "doc": "wordcraft", "odt": "wordcraft", "rtf": "wordcraft", "md": "wordcraft",
    "xlsx": "gridcraft", "csv": "gridcraft", "tsv": "gridcraft", "ods": "gridcraft",
    "pptx": "deckcraft", "deckcraft": "deckcraft",
    "dxf": "cadcraft", "dwg": "cadcraft",
    "wav": "soundcraft", "flac": "soundcraft", "mp3": "soundcraft", "mid": "soundcraft",
    "pdf": "pdfcraft", "svg": "vectorcraft", "ai": "vectorcraft",
    "png": "photocraft", "jpg": "photocraft", "jpeg": "photocraft", "webp": "photocraft", "psd": "photocraft",
    "mp4": "filmcraft", "mov": "filmcraft", "webm": "filmcraft", "mkv": "filmcraft",
    "idml": "designcraft", "fig": "figcraft", "dng": "lightcraft", "heic": "lightcraft",
}
MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf", "odt": "application/vnd.oasis.opendocument.text", "rtf": "application/rtf",
    "html": "text/html", "md": "text/markdown", "csv": "text/csv", "svg": "image/svg+xml",
    "dxf": "image/vnd.dxf", "png": "image/png", "gif": "image/gif", "txt": "text/plain",
}
FORMATS = {"doc": {"docx", "pdf", "odt", "rtf", "html", "md", "txt"},
           "sheet": {"xlsx", "pdf", "html", "csv", "json"},
           "deck": {"pptx", "pdf", "md", "gif"}}


def token():
    if not os.path.exists(TOKEN_FILE):
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, base64.urlsafe_b64encode(os.urandom(24)).rstrip(b"="))
        os.close(fd)
    return open(TOKEN_FILE).read().strip()


def binary(app, cli=False):
    name = app + ("-cli" if cli else "")
    p = os.path.join(APPS_DIR, app, "bin", name)
    if os.path.exists(p):
        return p
    return shutil.which(name)


def safe_name(name, ext):
    base = re.sub(r"[^A-Za-z0-9 ._()-]+", "", os.path.basename(str(name or "document"))).strip(" .")[:80] or "document"
    base = re.sub(r"\.[A-Za-z0-9]{1,9}$", "", base)
    return f"{base}.{ext}"


def unique(path):
    root, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(path):
        path = f"{root} ({i}){ext}"; i += 1
    return path


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "conversion failed").strip()[-600:])
    return r.stdout


def public_url(url):
    """Only http(s) URLs whose host resolves to public addresses (no LAN/loopback/metadata: SSRF guard)."""
    import ipaddress, socket
    from urllib.parse import urlparse
    try:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        for info in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80)):
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                return False
        return True
    except Exception:
        return False


SHOT_SEM = threading.Semaphore(2)


def screenshot(url, width=1280, height=800, out_w=640):
    if not public_url(url):
        raise ValueError("only public http(s) URLs")
    with SHOT_SEM, tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "s.jpeg")
        subprocess.run(["chromium", "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
                        "--no-first-run", "--disable-extensions", f"--user-data-dir={tmp}/p", f"--window-size={width},{height}",
                        "--virtual-time-budget=5000", f"--screenshot={out}", url],
                       cwd=tmp, capture_output=True, timeout=25)
        if not os.path.exists(out):
            raise RuntimeError("screenshot failed")
        try:
            from PIL import Image
            im = Image.open(out).convert("RGB")
            im.thumbnail((out_w, out_w * 2))
            im.save(out, "JPEG", quality=70, optimize=True)
        except Exception:
            pass
        return open(out, "rb").read()


def fetch(url, limit=40 * 1024 * 1024):
    if not public_url(url):
        return None
    try:
        class Guard(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                if not public_url(newurl):
                    raise urllib.error.HTTPError(newurl, 403, "redirect to private address", hdrs, fp)
                return super().redirect_request(req, fp, code, msg, hdrs, newurl)
        req = urllib.request.Request(url, headers={"User-Agent": "ZabilityCraftBridge/1.1 (self-hosted Intelligent WebUI)"})
        with urllib.request.build_opener(Guard).open(req, timeout=8) as r:
            data = r.read(limit + 1)
        return data if len(data) <= limit else None
    except Exception:
        return None


def shrink(data, max_px=1600):
    """Keep decks small: downscale big photos to max_px and re-encode as JPEG."""
    if not data:
        return data
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        if max(im.size) <= max_px and len(data) < 600_000:
            return data
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82, optimize=True)
        return buf.getvalue()
    except Exception:
        return data


def make_doc(d, tmp, out):
    src = os.path.join(tmp, "in.md")
    open(src, "w", encoding="utf-8").write(str(d.get("markdown") or d.get("content") or ""))
    run([binary("wordcraft", True), "convert", src, out], tmp)


def make_sheet(d, tmp, out):
    rows = d.get("rows")
    if rows:
        import csv, io
        buf = io.StringIO(); w = csv.writer(buf)
        if d.get("columns"):
            w.writerow(d["columns"])
        for r in rows:
            w.writerow(r if isinstance(r, list) else [r])
        text = buf.getvalue()
    else:
        text = str(d.get("csv") or d.get("content") or "")
    src = os.path.join(tmp, "in.csv")
    open(src, "w", encoding="utf-8").write(text)
    run([binary("gridcraft", True), "convert", src, out], tmp)


def make_deck(d, tmp, out):
    cmds = []
    new = {}
    if d.get("theme"):
        new["theme"] = str(d["theme"])
    cmds.append("file.new=" + json.dumps(new))
    slides = d.get("slides") or []
    if not slides and d.get("markdown"):
        cmds.append("slide.fromOutline=" + json.dumps({"text": d["markdown"], "markdown": True}))
    from concurrent.futures import ThreadPoolExecutor
    slides = slides[:60]
    with ThreadPoolExecutor(6) as ex:  # fetch all slide photos in parallel
        imgs = list(ex.map(lambda s: shrink(fetch(s.get("image"))) if isinstance(s, dict) and s.get("image") else None, slides))
    for i, s in enumerate(slides):
        title = str(s.get("title") or "")
        body = s.get("body") or s.get("bullets") or ""
        if isinstance(body, list):
            body = "\n".join(str(b) for b in body)
        img = imgs[i]
        chart = s.get("chart")
        if i == 0 and s.get("layout", "title") == "title" and not img and not chart:
            cmds.append("slide.new=" + json.dumps({"layout": "title", "title": title, "body": str(body)}))
        elif img or chart:
            cmds.append("slide.new=" + json.dumps({"layout": "titleOnly", "title": title}))
            if body:
                cmds.append("insert.textBox=" + json.dumps({"rect": [48, 130, 420, 360], "text": str(body)}))
            if img:
                cmds.append("insert.picture=" + json.dumps({"data": base64.b64encode(img).decode(), "name": "image", "rect": [492, 130, 420, 360]}))
            elif chart:
                c = {"type": chart.get("type", "column"), "rect": [492 if body else 120, 130, 420 if body else 720, 360],
                     "categories": chart.get("categories", []), "series": chart.get("series", [])}
                cmds.append("insert.chart=" + json.dumps(c))
        else:
            cmds.append("slide.new=" + json.dumps({"layout": s.get("layout", "titleAndContent"), "title": title, "body": str(body)}))
        if s.get("notes"):
            cmds.append("slide.notes=" + json.dumps({"text": str(s["notes"])}))
    cmds.append('slide.delete={"index":0}')  # the empty title slide every new deck starts with
    cf = os.path.join(tmp, "cmds.txt")
    open(cf, "w", encoding="utf-8").write("\n".join(cmds) + "\n")
    run([binary("deckcraft", True), "run", "--cmd-file", cf, "--save", out], tmp)


MAKERS = {"doc": make_doc, "sheet": make_sheet, "deck": make_deck}


def launch(app, path=None):
    exe = binary(app)
    if not exe:
        raise RuntimeError(f"{app} is not installed")
    env = dict(os.environ)
    env.update({"HOME": HOME, "XDG_RUNTIME_DIR": os.path.join(HOME, ".XDG"), "WAYLAND_DISPLAY": "wayland-0",
                "DISPLAY": ":0"})  # Xwayland of the Selkies app compositor
    args = [exe] + ([path] if path else [])
    subprocess.Popen(args, env=env, cwd=INBOX, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return exe


class H(BaseHTTPRequestHandler):
    server_version = "CraftBridge/1.0"

    def log_message(self, fmt, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _auth(self):
        got = self.headers.get("X-Craft-Token", "")
        return bool(got) and hmac.compare_digest(got, token())

    def do_GET(self):
        if self.path.split("?")[0] == "/health":
            return self._send(200, {"ok": True, "apps": {a: bool(binary(a)) for a in APPS},
                                    "formats": {k: sorted(v) for k, v in FORMATS.items()}})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._auth():
            return self._send(401, {"error": "bad token"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self._send(413, {"error": "body size"})
        try:
            d = json.loads(self.rfile.read(n))
        except Exception:
            return self._send(400, {"error": "bad json"})
        p = self.path.split("?")[0]
        try:
            if p == "/make":
                return self._send(200, self.make(d))
            if p == "/open":
                return self._send(200, self.open(d))
            if p == "/screenshot":
                img = screenshot(str(d.get("url", "")))
                return self._send(200, {"mime": "image/jpeg", "b64": base64.b64encode(img).decode(), "size": len(img)})
            if p == "/launch":
                app = str(d.get("app", ""))
                if app not in APPS:
                    raise ValueError("unknown app")
                launch(app)
                return self._send(200, {"opened": True, "app": app})
        except Exception as e:  # noqa
            return self._send(500, {"error": str(e)[:600]})
        self._send(404, {"error": "not found"})

    def make(self, d):
        kind = str(d.get("kind", "doc"))
        fmt = str(d.get("format") or {"doc": "docx", "sheet": "xlsx", "deck": "pptx"}.get(kind, "")).lower()
        if kind not in MAKERS or fmt not in FORMATS[kind]:
            raise ValueError(f"unsupported {kind}/{fmt}")
        name = safe_name(d.get("name"), fmt)
        t0 = time.time()
        with LOCK, tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, name)
            MAKERS[kind](d, tmp, out)
            data = open(out, "rb").read()
        res = {"name": name, "mime": MIME.get(fmt, "application/octet-stream"), "size": len(data),
               "b64": base64.b64encode(data).decode(), "ms": int((time.time() - t0) * 1000)}
        res["app"] = EXT_APP.get(fmt, "wordcraft")
        if d.get("open") or d.get("inbox"):
            os.makedirs(INBOX, exist_ok=True)
            path = unique(os.path.join(INBOX, name))
            open(path, "wb").write(data)
            res["path"] = path
            if d.get("open"):
                launch(res["app"], path)
                res["opened"] = True
        return res

    def open(self, d):
        url = str(d.get("url") or "")
        name = os.path.basename(str(d.get("name") or (url.split("?")[0].rstrip("/").rsplit("/", 1)[-1] if url else "") or "file.bin"))
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else "bin"
        app = str(d.get("app") or EXT_APP.get(ext, ""))
        if app not in APPS:
            raise ValueError(f"no craft app for .{ext}")
        if url:
            data = fetch(url)
            if data is None:
                raise ValueError("could not download that URL (public http(s) only, 40 MB max)")
            if ext == "bin" or ext not in EXT_APP:
                ext = {"photocraft": "png", "lightcraft": "jpg", "pdfcraft": "pdf", "vectorcraft": "svg",
                       "filmcraft": "mp4", "soundcraft": "wav"}.get(app, "bin")
                if data[:3] == b"\xff\xd8\xff":
                    ext = "jpg"
                elif data[:4] == b"\x89PNG":
                    ext = "png"
                elif data[:4] == b"%PDF":
                    ext = "pdf"
        else:
            data = base64.b64decode(d.get("b64") or "")
        os.makedirs(INBOX, exist_ok=True)
        path = unique(os.path.join(INBOX, safe_name(name, ext)))
        open(path, "wb").write(data)
        launch(app, path)
        return {"opened": True, "app": app, "path": path}


if __name__ == "__main__":
    token()
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    except OSError:
        raise SystemExit(0)  # already running
    srv.serve_forever()
