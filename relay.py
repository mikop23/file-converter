"""
온라인 AI - 중계 서버(server/worker.js)를 통해 Claude 사용
  서버 주소: 사용자 설정(config.json) → 빌드할 때 넣은 기본값(edition.json) 순서로 결정
"""
import base64, io, json, os, urllib.request
from pathlib import Path

import fconv


# ───────── 에디션 / 설정 ─────────
def _read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}

def config_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    d = Path(base) / "FileConverter"
    d.mkdir(parents=True, exist_ok=True)
    return d / "config.json"

def load_config():
    return _read_json(config_path())

def save_config(**kw):
    c = load_config(); c.update(kw)
    config_path().write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")

def server_url():
    url = os.environ.get("FCONV_RELAY") or load_config().get("relay_url") \
        or _read_json(fconv.APP_DIR / "edition.json").get("relay_url") or ""
    return url.rstrip("/")


# ───────── 서버 호출 ─────────
def _post(path, payload, timeout=60):
    url = server_url()
    if not url:
        raise ConnectionError("서버 주소가 설정되지 않았어요")
    req = urllib.request.Request(url + path, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("error")
        except Exception:
            msg = None
        raise ConnectionError(msg or f"서버 오류 (HTTP {e.code})")
    except urllib.error.URLError:
        raise ConnectionError("서버에 연결할 수 없어요 (인터넷 확인)")

def health():
    """서버가 살아 있고 AI 키가 있으면 True"""
    url = server_url()
    if not url:
        return False
    try:
        with urllib.request.urlopen(url + "/health", timeout=4) as r:
            return bool(json.load(r).get("ai"))
    except Exception:
        return False

def plan(text, files):
    return _post("/plan", {"text": text, "files": files[:300]}, timeout=30)["plan"]


# ───────── 글자 추출 (OCR) ─────────
def _jpeg_b64(im, max_side=1568):
    """Claude가 읽기 좋은 크기로 줄여서 base64 (5MB 제한 안쪽)"""
    im = im.convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    for q in (85, 70, 55):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q)
        if buf.tell() < 3_500_000:
            break
    return base64.b64encode(buf.getvalue()).decode()

def ocr_image(im):
    return _post("/ocr", {"image": _jpeg_b64(im), "media_type": "image/jpeg"}, timeout=120)["text"]

def pages_of(path, rot=0):
    """사진 1장 → [이미지], PDF → [페이지 이미지...]"""
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(p))
        try:
            return [page.render(scale=150 / 72).to_pil() for page in doc]
        finally:
            doc.close()
    return [fconv.load_image(p, 0, rot)]

def ocr_files(paths, target, out, progress=None, rotations=None):
    """사진/PDF 여러 개 → 글자 뽑아서 문서 하나로. progress(완료, 전체)"""
    jobs = [(p, i, im) for p in paths for i, im in enumerate(pages_of(p, (rotations or {}).get(str(p), 0)), 1)]
    parts, last = [], None
    for n, (p, i, im) in enumerate(jobs, 1):
        text = ocr_image(im)
        if len(paths) > 1 and p != last:
            parts.append(f"## {Path(p).name}")
        last = p
        if text:
            parts.append(text)
        if progress:
            progress(n, len(jobs))
    md = "\n\n".join(parts).strip()
    if not md:
        raise ValueError("글자를 찾지 못했어요")
    return fconv.text_to_document(md, target, out)
