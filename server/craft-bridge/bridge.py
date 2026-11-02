#!/usr/bin/env python3
"""Zability Craft Bridge - lets Frontier UI create real Office files with the
Craft CLIs and open them in the streamed Craft desktop. Stdlib only. LAN/internal only.

Endpoints (all but /health need header X-Craft-Token):
  GET  /health                -> {ok, apps}
  POST /make  {kind, format, name, open, ...content}  -> {name, mime, size, b64}
  POST /open  {name, b64, app?}                         -> {opened, app, path}
  POST /inspect  {name, b64, app?}                      -> {app, text, info, preview}
  POST /edit     {name, b64, commands:[{command, params}], out?, app?, extra?}  -> edited file
  POST /convert  {name, b64, format}                    -> converted file
  POST /commands {app, search?}                         -> the app's command catalogue (filtered)
  POST /cli      {app, args:[...], files:{name: b64}, timeout?, inbox?}  -> run <app>-cli in a scratch folder:
                 {exit_code, stdout, stderr, files:{name: b64} (new or changed files)}
"""
import base64, hmac, json, os, re, shutil, subprocess, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOME = os.environ.get("HOME", "/config")
INBOX = os.path.join(HOME, "Inbox")
APPS_DIR = os.path.join(HOME, "apps")
TOKEN_FILE = os.path.join(HOME, ".craft-bridge-token")
PORT = int(os.environ.get("CRAFT_BRIDGE_PORT", "8790"))
MAX_BODY = 400 * 1024 * 1024
LOCK = threading.Lock()
WORK = threading.Semaphore(2)

APPS = ["wordcraft", "gridcraft", "deckcraft", "cadcraft", "soundcraft", "photocraft", "vectorcraft",
        "filmcraft", "lightcraft", "pdfcraft", "effectcraft", "designcraft", "figcraft", "solidcraft",
        "texturecraft", "craft-anything", "artcraft-launcher"]
EXT_APP = {
    "docx": "wordcraft", "doc": "wordcraft", "odt": "wordcraft", "rtf": "wordcraft", "md": "wordcraft",
    "dotx": "wordcraft", "docm": "wordcraft", "tex": "wordcraft", "txt": "wordcraft",
    "xlsx": "gridcraft", "xlsm": "gridcraft", "xlsb": "gridcraft", "csv": "gridcraft", "tsv": "gridcraft", "ods": "gridcraft",
    "pptx": "deckcraft", "potx": "deckcraft", "ppsx": "deckcraft", "deckcraft": "deckcraft",
    "dxf": "cadcraft", "dwg": "cadcraft", "dwt": "cadcraft",
    "step": "solidcraft", "stp": "solidcraft", "stl": "solidcraft", "3mf": "solidcraft", "iges": "solidcraft",
    "igs": "solidcraft", "sc": "solidcraft",
    "wav": "soundcraft", "flac": "soundcraft", "mp3": "soundcraft", "mid": "soundcraft", "aif": "soundcraft",
    "aiff": "soundcraft", "ogg": "soundcraft", "m4a": "soundcraft", "aac": "soundcraft", "scraft": "soundcraft",
    "pdf": "pdfcraft", "svg": "vectorcraft", "ai": "vectorcraft", "eps": "vectorcraft", "emf": "vectorcraft",
    "png": "photocraft", "jpg": "photocraft", "jpeg": "photocraft", "webp": "photocraft", "psd": "photocraft",
    "gif": "photocraft", "bmp": "photocraft", "tif": "photocraft", "tiff": "photocraft", "avif": "photocraft",
    "kra": "photocraft", "pcraft": "photocraft", "exr": "photocraft",
    "mp4": "filmcraft", "mov": "filmcraft", "webm": "filmcraft", "mkv": "filmcraft", "avi": "filmcraft", "mxf": "filmcraft",
    "idml": "designcraft", "fig": "figcraft", "figcraft": "figcraft", "sketch": "figcraft", "penpot": "figcraft",
    "dng": "lightcraft", "heic": "lightcraft", "cr2": "lightcraft", "cr3": "lightcraft", "nef": "lightcraft",
    "arw": "lightcraft", "raf": "lightcraft", "orf": "lightcraft", "rw2": "lightcraft", "pef": "lightcraft",
    "ecproj": "effectcraft",
    **{e: "texturecraft" for e in "tcraft glb gltf fbx dae usd usda usdc usdz abc obj ply".split()},
}
# anything else (zip, exe, apk, app bundles, unknown binaries) is looked at by Craft Anything's triage
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
        req = urllib.request.Request(url, headers={"User-Agent": "ZabilityCraftBridge/1.1 (self-hosted Frontier UI)"})
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


# ---------------- read / edit / convert any Craft-supported file ----------------
def soft(cmd, cwd, timeout=120, limit=40000):
    """Run a CLI step and return (ok, text) without raising."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + ("" if r.returncode == 0 else "\n" + (r.stderr or "")[-800:])
        return r.returncode == 0, out[:limit]
    except Exception as e:
        return False, str(e)[:400]


def app_for(name, app=None):
    if app:
        if app not in APPS:
            raise ValueError(f"unknown app {app}")
        return app
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return EXT_APP.get(ext, "craft-anything")


def preview_b64(path, max_px=1000):
    try:
        from PIL import Image
        import io
        im = Image.open(path).convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=78, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def stage(tmp, d, key="name", bkey="b64"):
    name = os.path.basename(str(d.get(key) or "file.bin")).replace("/", "_") or "file.bin"
    name = re.sub(r"[^\w .()+-]+", "", name) or "file.bin"
    p = os.path.join(tmp, "in", name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(base64.b64decode(d.get(bkey) or ""))
    return p


def inspect_file(d):
    with tempfile.TemporaryDirectory() as tmp:
        p = stage(tmp, d)
        app = app_for(p, d.get("app"))
        c, png, res = binary(app, True), os.path.join(tmp, "preview.png"), {"app": app}
        text = info = ""
        if app == "wordcraft":
            _, text = soft([c, "text", p], tmp)
            _, info = soft([c, "info", p], tmp)
            soft([c, "render", p, png, "--page", "1", "--scale", "1"], tmp)
        elif app == "gridcraft":
            _, info = soft([c, "info", p, "--json"], tmp)
            sheets = []
            try:
                sheets = [s.get("name") for s in json.loads(info).get("sheets", []) if isinstance(s, dict)]
            except Exception:
                pass
            parts = []
            for s in (sheets or [None])[:6]:
                ok, csv_text = soft([c, "cat", p, "--csv"] + (["--sheet", s] if s else []), tmp, limit=12000)
                parts.append((f"## Sheet: {s}\n" if s else "") + csv_text)
            text = "\n\n".join(parts)
            ok, f = soft([c, "cat", p, "--formulas", "--csv"], tmp, limit=8000)
            if ok and "=" in f:
                res["formulas"] = f
        elif app == "deckcraft":
            _, info = soft([c, "info", p], tmp)
            md = os.path.join(tmp, "outline.md")
            if soft([c, "convert", p, md], tmp)[0] and os.path.exists(md):
                text = open(md, encoding="utf-8", errors="replace").read()[:30000]
            soft([c, "render", p, "--slide", "0", "--scale", "1", png], tmp)
        elif app == "pdfcraft":
            _, info = soft([c, "info", p], tmp)
            _, text = soft([c, "text", p], tmp)
            soft([c, "render", p, "--page", "1", "--dpi", "72", "--out", png], tmp)
        elif app in ("photocraft",):
            _, info = soft([c, "info", p, "--compact"], tmp)
            if not preview_b64(p):
                soft([c, "convert", p, png], tmp)
            else:
                shutil.copy(p, png) if p.lower().endswith(".png") else soft([c, "convert", p, png], tmp)
        elif app == "lightcraft":
            soft([c, "render", p, "-o", os.path.join(tmp, "preview.jpg"), "--size", "1200"], tmp)
            png = os.path.join(tmp, "preview.jpg")
        elif app == "vectorcraft":
            soft([c, "convert", p, png], tmp)
            if p.lower().endswith(".svg"):
                text = open(p, encoding="utf-8", errors="replace").read()[:20000]
        elif app == "cadcraft":
            _, info = soft([c, "info", p, "--compact"], tmp)
            soft([c, "convert", p, png], tmp)
        elif app == "solidcraft":
            j = os.path.join(tmp, "eval.json")
            soft([c, "eval", "--in", p, "--json-out", j], tmp, timeout=180)
            info = open(j).read()[:15000] if os.path.exists(j) else ""
            soft([c, "snapshot", "--in", p, "--out", png, "--width", "1000", "--height", "700"], tmp, timeout=180)
        elif app == "figcraft":
            _, info = soft([c, "info", p], tmp)
            soft([c, "render", p, "--out", png], tmp)
        elif app == "designcraft":
            soft([c, "run", "--in", p, "--page", "1", "--scale", "1", "--export", png], tmp)
            pdf = os.path.join(tmp, "t.pdf")
            if soft([c, "run", "--in", p, "--export", pdf], tmp)[0]:
                _, text = soft([binary("pdfcraft", True), "text", pdf], tmp)
        elif app == "soundcraft":
            _, info = soft([c, "info", p], tmp)
        elif app == "filmcraft":
            _, info = soft([c, "probe", p], tmp)
        elif app == "effectcraft":
            _, info = soft([c, "info", p], tmp)
        elif app == "texturecraft":
            _, info = soft([c, "info", p], tmp)
            soft([c, "render", p, png, "--size", "1000x700"], tmp, timeout=180)
        else:  # craft-anything: first look at any other file (deep = may read the file's contents; never runs it)
            _, text = soft([c, "triage", p, "--format", "md", "--deep"], tmp, timeout=180)
        res.update({"name": os.path.basename(p), "size": os.path.getsize(p), "text": text[:30000], "info": info[:15000]})
        for cand in (png, os.path.join(tmp, "preview.jpg")):
            if os.path.exists(cand):
                res["preview"] = preview_b64(cand)
                break
        return res


def _jsonl(tmp, name, steps, key="command"):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        for s in steps:
            f.write(json.dumps({key: s.get("command") or s.get("id"), "params": s.get("params") or {}}) + "\n")
    return path


def edit_file(d):
    steps = d.get("commands") or []
    if isinstance(steps, str):
        steps = json.loads(steps)
    steps = [s if isinstance(s, dict) else {"command": str(s)} for s in steps][:500]
    with tempfile.TemporaryDirectory() as tmp:
        p = stage(tmp, d)
        app = app_for(p, d.get("app"))
        c = binary(app, True)
        in_ext = p.rsplit(".", 1)[-1].lower() if "." in p else "bin"
        out_name = safe_name(d.get("out") or os.path.basename(p).rsplit(".", 1)[0] + " (edited)",
                             (str(d.get("out")).rsplit(".", 1)[-1].lower() if d.get("out") and "." in str(d.get("out")) else in_ext))
        out = os.path.join(tmp, out_name)
        if app == "wordcraft":
            s = os.path.join(tmp, "s.json")
            json.dump({"commands": [{"command": x.get("command"), "params": x.get("params") or {}} for x in steps]}, open(s, "w"))
            run([c, "run", "--file", p, "--script", s, "--save", out], tmp)
        elif app == "gridcraft":
            run([c, "run", "--in", p, "--script", _jsonl(tmp, "s.jsonl", steps), "--out", out, "--quiet"], tmp)
        elif app == "deckcraft":
            cf = os.path.join(tmp, "c.txt")
            open(cf, "w").write("\n".join(f"{x.get('command')}={json.dumps(x.get('params') or {})}" for x in steps) + "\n")
            run([c, "run", "--in", p, "--cmd-file", cf, "--save", out], tmp)
        elif app == "vectorcraft":
            s = os.path.join(tmp, "s.json")
            json.dump([{"command": x.get("command"), "params": x.get("params") or {}} for x in steps], open(s, "w"))
            run([c, "run", "--in", p, "--commands", s, "--export", out], tmp)
        elif app == "photocraft":
            args = [c, "run", p]
            for x in steps:
                args += ["--cmd", x.get("command"), "--params", json.dumps(x.get("params") or {})]
            run(args + ["--out", out], tmp)
        elif app == "cadcraft":
            args = [c, "run", p]
            for x in steps:
                args += ["--cmd", f"{x.get('command')} {json.dumps(x.get('params') or {})}"]
            run(args + ["--save", out], tmp)
        elif app == "figcraft":
            s = os.path.join(tmp, "s.json")
            json.dump([{"command": x.get("command"), "params": x.get("params") or {}} for x in steps], open(s, "w"))
            run([c, "run", s, "--in", p, "--out", out], tmp)
        elif app == "designcraft":
            args = [c, "run", "--in", p]
            for x in steps:
                args += ["--cmd", f"{x.get('command')}={json.dumps(x.get('params') or {})}"]
            run(args + ["--export", out], tmp)
        elif app == "solidcraft":
            s = os.path.join(tmp, "s.json")
            json.dump([{"command": x.get("command"), "params": x.get("params") or {}} for x in steps], open(s, "w"))
            run([c, "run", s, "--in", p, "--out", out], tmp)
        elif app == "texturecraft":
            if not out.lower().endswith(".tcraft"):
                out = out.rsplit(".", 1)[0] + ".tcraft"
            s = os.path.join(tmp, "s.json")
            json.dump({"open": p, "steps": [{"id": x.get("command"), "params": x.get("params") or {}} for x in steps], "save": out}, open(s, "w"))
            run([c, "batch", s], tmp)
        elif app == "effectcraft":
            s = os.path.join(tmp, "s.json")
            json.dump([{"command": x.get("command"), "params": x.get("params") or {}} for x in steps], open(s, "w"))
            run([c, "run", "--commands", s], tmp)
            out = p
        elif app == "lightcraft":
            args = [c, "run", "--import", p]
            for x in steps:
                args.append(x.get("command"))
                args += [f"{k}={json.dumps(v) if not isinstance(v, str) else v}" for k, v in (x.get("params") or {}).items()]
            if not out.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".webp", ".avif", ".dng", ".psd")):
                out = out.rsplit(".", 1)[0] + ".jpg"
            run(args + ["app.export", f"path={out}"], tmp)
        elif app == "soundcraft":
            args = [c, "run"]
            if in_ext == "scraft":
                args += ["--in", p]
            else:
                steps = [{"command": "file.import", "params": {"path": p}}] + steps
            for x in steps:
                args += ["--cmd", f"{x.get('command')}={json.dumps(x.get('params') or {})}"]
            if not out.lower().endswith((".wav", ".flac", ".aif", ".aiff", ".mp3")):
                out = out.rsplit(".", 1)[0] + ".wav"
            run(args + ["--bounce", out], tmp)
        elif app == "filmcraft":
            s = os.path.join(tmp, "s.jsonl")
            with open(s, "w") as f:
                f.write(json.dumps({"id": "file.import", "params": {"paths": [p]}}) + "\n")
                for x in steps:
                    f.write(json.dumps({"id": x.get("command"), "params": x.get("params") or {}}) + "\n")
            run([c, "run", s], tmp)
            if not out.lower().endswith((".mp4", ".mov", ".webm", ".gif", ".wav")):
                out = out.rsplit(".", 1)[0] + ".mp4"
            run([c, "export", out], tmp)
        elif app == "pdfcraft":
            ops, extra = [], []
            for x in steps:
                op, pr = x.get("command"), x.get("params") or {}
                if op == "rotate":
                    ops += ["--rotate", f"{pr.get('pages')}:{pr.get('angle', 90)}"]
                elif op == "delete":
                    ops += ["--delete", str(pr.get("pages"))]
                elif op == "move":
                    ops += ["--move", f"{pr.get('from')}:{pr.get('to')}"]
                elif op == "insert-blank":
                    ops += ["--insert-blank", str(pr.get("after", 1))]
                elif op in ("title", "author"):
                    ops += [f"--{op}", str(pr.get("value", ""))]
                elif op == "extract":
                    run([c, "extract", p, "--pages", str(pr.get("pages")), "--out", out], tmp)
                    p = out
                elif op == "combine":
                    for i, f in enumerate(d.get("extra") or []):
                        extra.append(stage(tmp, {"name": f"x{i}_" + str(f.get("name", "x.pdf")), "b64": f.get("b64")}))
                    run([c, "combine", p] + extra + ["--out", out], tmp)
                    p = out
                else:
                    raise ValueError(f"unknown pdf op {op}: use rotate, delete, move, insert-blank, title, author, extract, combine")
            if ops:
                tmp_out = out + ".tmp.pdf"
                run([c, "edit", p, "--out", tmp_out] + ops, tmp)
                shutil.move(tmp_out, out)
            elif p != out:
                shutil.copy(p, out)
        else:
            raise ValueError(f"{app} files can be read but not edited headlessly")
        if not os.path.exists(out):
            raise RuntimeError("the app finished but wrote no file")
        if os.path.getsize(out) > 60 * 1024 * 1024:
            raise ValueError('the result is larger than 60 MB; choose a lighter format')
        data = open(out, "rb").read()
        ext = out.rsplit(".", 1)[-1].lower()
        return {"app": app, "name": os.path.basename(out), "mime": MIME.get(ext, "application/octet-stream"),
                "size": len(data), "b64": base64.b64encode(data).decode()}


def convert_file(d):
    fmt = str(d.get("format") or "").lower().strip(". ")
    if not re.match(r"^[a-z0-9]{1,8}$", fmt):
        raise ValueError("format must be a file extension like pdf, docx, png")
    with tempfile.TemporaryDirectory() as tmp:
        p = stage(tmp, d)
        app = app_for(p, d.get("app"))
        c = binary(app, True)
        out = os.path.join(tmp, safe_name(os.path.basename(p).rsplit(".", 1)[0], fmt))
        if app in ("wordcraft", "gridcraft", "deckcraft", "cadcraft", "photocraft", "vectorcraft", "figcraft", "soundcraft"):
            run([c, "convert", p, out], tmp)
        elif app == "lightcraft":
            run([c, "render", p, "-o", out], tmp)
        elif app == "pdfcraft":
            if fmt == "txt":
                open(out, "w").write(soft([c, "text", p], tmp)[1])
            elif fmt in ("png", "jpg", "tif"):
                run([c, "render", p, "--page", str(d.get("page") or 1), "--out", out], tmp)
            elif fmt in ("docx", "md", "html", "odt", "rtf"):  # PdfCraft text -> WordCraft document
                md = os.path.join(tmp, "text.md")
                pages = soft([c, "text", p], tmp, limit=5_000_000)[1].split("\f")
                open(md, "w", encoding="utf-8").write("\n\n---\n\n".join(pg.strip() for pg in pages if pg.strip()))
                run([binary("wordcraft", True), "convert", md, out], tmp)
            else:
                raise ValueError("PDF converts to txt, png, jpg, tif, docx, md, html, odt or rtf")
        elif app == "solidcraft":
            run([c, "run", "--in", p, "--out", out], tmp, )
        elif app == "texturecraft":
            if fmt == "tcraft":  # mesh -> new project with a smart material
                run([c, "new", p, out, "--sample"], tmp)
            else:  # export the texture maps as a zip of images
                d2 = os.path.join(tmp, "textures")
                run([c, "export", p, d2] + ([] if fmt == "zip" else ["--format", fmt]), tmp)
                out = shutil.make_archive(os.path.join(tmp, os.path.basename(p).rsplit(".", 1)[0] + "-textures"), "zip", d2)
        elif app == "designcraft":
            run([c, "run", "--in", p, "--export", out], tmp)
        elif app == "filmcraft":
            s = os.path.join(tmp, "s.jsonl")
            open(s, "w").write(json.dumps({"id": "file.import", "params": {"paths": [p]}}) + "\n")
            run([c, "run", s], tmp)
            run([c, "export", out], tmp)
        else:
            raise ValueError(f"{app} has no converter")
        if os.path.getsize(out) > 60 * 1024 * 1024:
            raise ValueError('the result is larger than 60 MB; choose a lighter format')
        data = open(out, "rb").read()
        return {"app": app, "name": os.path.basename(out), "mime": MIME.get(fmt, "application/octet-stream"),
                "size": len(data), "b64": base64.b64encode(data).decode()}


CMD_CACHE = {}


def list_commands(d):
    app = str(d.get("app") or "")
    if app not in APPS or app in ("artcraft-launcher",):
        raise ValueError("app must be one of " + ", ".join(a for a in APPS if a != "artcraft-launcher"))
    if app == "pdfcraft":
        return {"app": app, "commands": "pdf ops for craft_edit: rotate {pages:'1,3', angle:90} · delete {pages:'2-4'} · move {from:5, to:1} · "
                                        "insert-blank {after:1} · title {value} · author {value} · extract {pages:'1,3,5-8'} · combine {} (with extra files)"}
    if app not in CMD_CACHE:
        with tempfile.TemporaryDirectory() as tmp:
            ok, txt = soft([binary(app, True), "commands", "--json"], tmp, timeout=60, limit=8_000_000)
            if not ok or txt.lstrip()[:1] not in "[{" or txt.strip() in ("[]", "{}"):
                ok, txt = soft([binary(app, True), "commands"], tmp, timeout=60, limit=8_000_000)
            CMD_CACHE[app] = txt
    text = CMD_CACHE[app]
    if text.lstrip()[:1] in "[{":  # some CLIs print the catalogue as JSON: flatten to one line per command
        try:
            j = json.loads(text)
            items = j if isinstance(j, list) else (j.get("commands") or list(j.values()))
            text = "\n".join(f"{it.get('id') or it.get('command')} — {it.get('label') or it.get('title') or ''}"
                             + (f"\n    params: {json.dumps(it.get('params'))[:400]}" if it.get("params") else "")
                             for it in items if isinstance(it, dict))
            CMD_CACHE[app] = text
        except Exception:
            pass
    q = [w for w in re.split(r"\W+", str(d.get("search") or "").lower()) if w]
    if q:  # keep matching command lines plus their indented parameter lines
        keep, blocks, cur = [], [], []
        for line in text.splitlines():
            if line and not line[0].isspace() and cur:
                blocks.append(cur); cur = []
            cur.append(line)
        if cur:
            blocks.append(cur)
        for b in blocks:
            joined = "\n".join(b)
            if all(w in joined.lower() for w in q):
                keep.append(joined)
        text = "\n".join(keep) or f"No {app} commands match '{d.get('search')}'."
    return {"app": app, "commands": text[:14000]}


CLI_DENY_SUB = {"mcp", "serve", "app", "setup", "uninstall", "plugin", "connect", "ui", "send", "zotero", "ai", "crashes",
                "bench-assistant", "fuzz", "oracle", "snapshot-ui", "engines_install", "settings_set", "plugins_install",
                "doctor", "rebuild"}
CLI_DENY_FLAG = ("--connect", "--bridge", "--allow-run", "--allow-any-path", "--allow-path", "--control", "--automation-",
                 "--read-root", "--write-root", "--root", "--library", "--token", "--port")
CLI_MAX_OUT = 200 * 1024 * 1024


def run_cli(d):
    """Run one app CLI in a fresh scratch folder with the given files staged; return stdout and every new or changed file.
    Agents (e.g. Hermes) get the whole CLI surface of the 16 apps without a shell: no absolute paths, no '..',
    no servers/bridges/AI backends, nothing that escapes the scratch folder."""
    app = str(d.get("app") or "")
    if app not in APPS or app == "artcraft-launcher":
        raise ValueError("app must be one of " + ", ".join(a for a in APPS if a != "artcraft-launcher"))
    exe = binary(app, True)
    if not exe:
        raise RuntimeError(f"{app}-cli is not installed")
    args = [str(a) for a in (d.get("args") or [])]
    if not args:
        raise ValueError("args is empty; e.g. [\"--help\"] or [\"commands\"]")
    for a in args:
        if a.startswith("/") or re.search(r"(^|[\\/=])\.\.([\\/]|$)", a) or "~" in a[:2]:
            raise ValueError(f"argument {a!r}: use file names relative to the job folder (no absolute paths or '..')")
        if a.split("=")[0].startswith(CLI_DENY_FLAG):
            raise ValueError(f"argument {a!r} is not allowed through the bridge")
    sub = next((a for a in args if a in CLI_DENY_SUB or a.replace("-", "_") in CLI_DENY_SUB), "")
    if sub:
        raise ValueError(f"'{sub}' is not available through the bridge")
    timeout = max(10, min(int(d.get("timeout") or 300), 1200))
    files = d.get("files") or {}
    with tempfile.TemporaryDirectory(prefix="cli-") as tmp:
        before = {}
        for name, b64 in files.items():
            rel = os.path.normpath(str(name)).lstrip("/\\")
            if rel.startswith("..") or os.path.isabs(rel):
                raise ValueError(f"bad file name {name!r}")
            p = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            raw = base64.b64decode(b64 or "")
            if len(raw) < 4_000_000 and re.search(rb'["\'=\s](/config|/etc|/root|/proc|/lsiopy|/home|/run)(/|["\'\s])', raw[:4_000_000]) \
                    and rel.rsplit(".", 1)[-1].lower() in ("json", "jsonl", "txt", "sc", "jsx", "js", "lua", "py", "sh", "yml", "yaml", "md"):
                raise ValueError(f"{name}: scripts may only use paths inside the job folder")
            open(p, "wb").write(raw)
            before[rel] = os.path.getmtime(p)
        if app == "craft-anything":  # its tools insist on absolute paths: point staged names at the job folder
            args = [os.path.join(tmp, a) if a in before else a for a in args]
        env = dict(os.environ)
        env.update({"HOME": HOME, "XDG_RUNTIME_DIR": os.path.join(HOME, ".XDG"), "NO_COLOR": "1"})
        t0 = time.time()
        try:
            r = subprocess.run([exe] + args, cwd=tmp, capture_output=True, timeout=timeout, env=env,
                               stdin=subprocess.DEVNULL)
            code, out, err = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired as e:
            code, out, err = -9, e.stdout or b"", (e.stderr or b"") + f"\n[timed out after {timeout}s]".encode()
        res = {"app": app, "exit_code": code, "ms": int((time.time() - t0) * 1000),
               "stdout": out.decode("utf-8", "replace")[-2_000_000:], "stderr": err.decode("utf-8", "replace")[-8000:], "files": {}}
        total = 0
        for root, _, names in os.walk(tmp):
            for n in names:
                p = os.path.join(root, n)
                rel = os.path.relpath(p, tmp)
                if os.path.islink(p) or (rel in before and os.path.getmtime(p) == before[rel]):
                    continue
                size = os.path.getsize(p)
                total += size
                if total > CLI_MAX_OUT:
                    res["truncated"] = "outputs over 200 MB were left out"
                    break
                res["files"][rel] = base64.b64encode(open(p, "rb").read()).decode()
        if d.get("inbox") and res["files"]:  # also drop results on the Craft desktop (Inbox/<folder>) to open by hand
            dest = os.path.join(INBOX, re.sub(r"[^A-Za-z0-9 ._-]+", "", str(d.get("inbox_folder") or "Hermes"))[:40] or "Hermes")
            os.makedirs(dest, exist_ok=True)
            res["inbox"] = []
            for rel, b64 in res["files"].items():
                p = unique(os.path.join(dest, os.path.basename(rel)))
                open(p, "wb").write(base64.b64decode(b64))
                res["inbox"].append(p)
        return res


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
            if p in ("/inspect", "/edit", "/convert"):
                with WORK:
                    return self._send(200, {"/inspect": inspect_file, "/edit": edit_file, "/convert": convert_file}[p](d))
            if p == "/commands":
                return self._send(200, list_commands(d))
            if p == "/cli":
                with WORK:
                    return self._send(200, run_cli(d))
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
            if os.path.getsize(out) > 60 * 1024 * 1024:
                raise ValueError('the result is larger than 60 MB; choose a lighter format')
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
    except OSError:  # already running (e.g. started by hand): wait before exiting so s6 doesn't restart-loop
        time.sleep(60)
        raise SystemExit(0)
    srv.serve_forever()
