#!/usr/bin/env python3
"""
fai - 말로 시키는 파일 변환 AI (fconv.py의 '입구')

준비 (Termux):
  pkg install ollama
  ollama serve &              # AI 서버 켜기 (백그라운드)
  ollama pull qwen2.5:3b      # 작은 모델 받기 (약 2GB, 처음 한 번)

사용:
  python fai.py                       # 대화 모드 (현재 폴더 기준)
  python fai.py -d ~/storage/dcim/Camera
  python fai.py "사진들 시간순으로 pdf로 묶어줘"

구조:  사용자 문장 → 로컬 AI가 '작업 계획(JSON)' 작성 → 검사 → 확인 → fconv 실행
AI는 명령어를 직접 실행하지 않고 계획만 세움 (안전). AI가 꺼져 있으면 규칙 기반으로 동작.
"""
import argparse, fnmatch, json, os, re, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fconv

API = os.environ.get("FAI_API", "http://127.0.0.1:11434/v1/chat/completions")  # Ollama 기본
MODEL = os.environ.get("FAI_MODEL", "qwen2.5:3b")

SYSTEM = """너는 파일 변환 도우미다. 사용자 요청을 아래 JSON 하나로만 답한다. 설명 금지.

가능한 action:
1) "bundle": 이미지 여러 장을 하나로 묶기. out 확장자는 pdf/docx/pptx/zip 중 하나.
   {"action":"bundle","files":["*.jpg"],"out":"묶음.pdf","sort":"name"|"time","quality":80,"max_size":2000,"per_page":1}
2) "convert": 문서 하나를 다른 형식으로. target은 docx/pdf/md/html/txt/odt/epub 중 하나.
   {"action":"convert","files":["보고서.md"],"target":"docx"}
3) "split": PDF를 페이지별 이미지로.
   {"action":"split","files":["스캔.pdf"],"format":"jpg"|"png"}
4) "unknown": 위로 처리 못하는 요청. {"action":"unknown","reason":"..."}

규칙:
- files에는 아래 '폴더 파일 목록'에 있는 이름이나 와일드카드(*.jpg)만 쓴다.
- "사진/이미지 전부" → 이미지 확장자 와일드카드. "찍은 순/시간순" → sort "time".
- "용량 줄여/작게" → quality 60, max_size 1500. "고화질/원본" → quality 95, max_size 0.
- "한 페이지에 N장" → per_page N.
- 출력 파일명을 말 안 하면 적당한 한국어 이름을 짓는다.

예시)
요청: 사진들 찍은 순서대로 피디에프로 합쳐줘
{"action":"bundle","files":["*.jpg","*.png"],"out":"사진모음.pdf","sort":"time","quality":80,"max_size":2000,"per_page":1}
요청: 보고서.docx pdf로 바꿔
{"action":"convert","files":["보고서.docx"],"target":"pdf"}"""

IMG_GLOBS = ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.heic", "*.JPG", "*.JPEG", "*.PNG"]


# ───────── AI 호출 ─────────
def list_models():
    """Ollama에 설치된 모델 목록. 서버 꺼져 있으면 None"""
    try:
        base = API.split("/v1/")[0]
        with urllib.request.urlopen(base + "/api/tags", timeout=2) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return None

FORMAT_WORDS = [  # 긴 단어 먼저 (피디에프 ⊃ 에프 같은 겹침 방지)
    ("파워포인트", "pptx"), ("피피티", "pptx"), ("ppt", "pptx"), ("pptx", "pptx"),
    ("워드", "docx"), ("word", "docx"), ("docx", "docx"),
    ("압축파일", "zip"), ("압축 파일", "zip"), ("집파일", "zip"), ("zip", "zip"),
    ("피디에프", "pdf"), ("pdf", "pdf"),
    ("마크다운", "md"), ("텍스트", "txt"), ("txt", "txt"), ("html", "html"), ("웹페이지", "html"),
    ("epub", "epub"), ("odt", "odt"),
    ("제이피지", "jpg"), ("제이펙", "jpg"), ("jpeg", "jpg"), ("jpg", "jpg"),
    ("피엔지", "png"), ("png", "png"), ("웹피", "webp"), ("webp", "webp"),
]
IMG_FMT = {"jpg", "png", "webp"}
SPLIT_WORDS = ["쪼개", "나눠", "나누", "분리", "페이지별", "장별"]

def hints(text, files):
    """문장에서 확실한 단서만 뽑기 (형식, 쪼개기, 장수, 순서, 화질)"""
    t = text.lower()
    for f in files:                                  # 파일명 속 확장자는 형식으로 안 봄
        t = t.replace(f.lower(), " ").replace(Path(f).stem.lower(), " ")
    fmt = None
    pos = len(t) + 1
    for word, ext in FORMAT_WORDS:                   # 문장에서 제일 마지막에 나온 형식 = 목표 형식
        i = t.rfind(word)
        if i >= 0 and (fmt is None or i > pos or (i == pos and len(word) > 0)):
            fmt, pos = ext, i
    n = re.search(r"(\d+)\s*장\s*씩|페이지[당에]?\s*(\d+)\s*장|한\s*(?:쪽|장|페이지)에\s*(\d+)", t)
    return {
        "fmt": fmt,
        "split": any(w in t for w in SPLIT_WORDS),
        "per_page": int(next(g for g in n.groups() if g)) if n else None,
        "time": any(w in t for w in ["시간", "찍은", "날짜", "촬영"]),
        "small": any(w in t for w in ["용량", "작게", "가볍", "압축해서"]),
        "hq": any(w in t for w in ["고화질", "원본", "화질 좋"]),
    }

def fix_plan(plan, text, files):
    """작은 AI가 자주 틀리는 부분을 확실한 단서로 바로잡기"""
    h = hints(text, files)
    act = plan.get("action")
    has_img = any(Path(f).suffix.lower() in fconv.IMG_EXT for f in files)
    if act == "split" and not h["split"]:            # 쪼개란 말 없는데 split → 묶기/변환으로
        act = plan["action"] = "bundle" if has_img and h["fmt"] in {"pdf", "docx", "pptx", "zip", None} else "convert"
        if act == "bundle":
            plan["files"] = IMG_GLOBS
    if act == "bundle":
        fl = plan.get("files") or []
        if not fl or all(any(c in f for c in "*?[") for f in fl):   # "사진 전부" → 모든 이미지 형식
            plan["files"] = IMG_GLOBS
        if not h["time"] and plan.get("sort") == "time":             # 시킨 적 없는 시간순은 취소
            plan["sort"] = "name"
        if h["fmt"] in {"pdf", "docx", "pptx", "zip"}:
            plan["out"] = Path(plan.get("out") or "묶음").stem + "." + h["fmt"]
        if h["per_page"]:
            plan["per_page"] = h["per_page"]
        if h["time"]:
            plan["sort"] = "time"
        if h["small"]:
            plan.update(quality=60, max_size=1500)
        if h["hq"]:
            plan.update(quality=95, max_size=0)
    elif act in ("convert", "imgconv") and h["fmt"] in IMG_FMT and has_img and not h["split"]:
        plan["action"], plan["target"] = "imgconv", h["fmt"]
        if not any(Path(f).suffix.lower() in fconv.IMG_EXT or any(c in f for c in "*?[") for f in plan.get("files") or []):
            plan["files"] = IMG_GLOBS
    elif act == "convert" and h["fmt"]:
        plan["target"] = h["fmt"]
    elif act == "ocr" and h["fmt"] in {"docx", "txt", "md"}:
        plan["target"] = h["fmt"]
    return plan

def ai_plan(text, files, model=None, api=None):
    return fix_plan(ask_ai(text, files, model, api), text, files)

def make_plan(text, files, model=None, api=None, online=False):
    """요청 → (검사된 계획, 'AI'|'규칙'). AI가 틀리면 규칙으로 한 번 더. 둘 다 실패 시 ValueError"""
    if online:
        import relay
        try:
            return check(fix_plan(relay.plan(text, files), text, files), files, allow_ocr=True), "온라인 AI"
        except Exception:
            pass
    if model:
        try:
            return check(ai_plan(text, files, model, api), files), "AI"
        except Exception:
            pass
    return check(ask_rules(text, files, ocr=online), files, allow_ocr=online), "규칙"

def ask_ai(text, files, model=None, api=None):
    listing = "\n".join(files[:200]) or "(비어 있음)"
    body = {
        "model": model or MODEL, "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"폴더 파일 목록:\n{listing}\n\n요청: {text}"},
        ],
    }
    req = urllib.request.Request(api or API, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        content = json.load(r)["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)          # 작은 모델이 말 붙여도 JSON만 추출
    return json.loads(m.group(0))


# ───────── AI 없을 때 쓰는 규칙 기반 해석 ─────────
OCR_WORDS = ["글자", "텍스트로", "타이핑", "ocr", "받아적", "받아 적", "글씨"]

def ask_rules(text, files, ocr=False):
    t = text.lower()
    named = [f for f in files if f.lower() in t or (len(Path(f).stem) >= 2 and Path(f).stem.lower() in t)]
    rest = t
    for f in named: rest = rest.replace(f.lower(), " ").replace(Path(f).stem.lower(), " ")   # 파일명 속 확장자는 형식으로 안 봄
    fmt = next((f for f in ["pptx", "docx", "pdf", "zip", "html", "md", "txt", "epub", "odt", "png", "jpg"]
                if f in rest), None)
    alias = {"피피티": "pptx", "ppt": "pptx", "파워포인트": "pptx", "워드": "docx", "word": "docx",
             "압축": "zip", "마크다운": "md", "텍스트": "txt", "웹": "html", "pdf": "pdf", "피디에프": "pdf"}
    for k, v in alias.items():
        if k in rest and not fmt: fmt = v

    if ocr and any(k in t for k in OCR_WORDS):
        src = named or [f for f in files if Path(f).suffix.lower() in fconv.IMG_EXT | {".pdf"}]
        tgt = "txt" if ("txt" in rest or "메모장" in t) else "md" if fmt == "md" else "docx"
        return {"action": "ocr", "files": src, "target": tgt}

    h = hints(text, files)
    has_img = any(Path(f).suffix.lower() in fconv.IMG_EXT for f in files)
    has_pdf = any(f.lower().endswith(".pdf") for f in files)
    if h["fmt"] in IMG_FMT and has_pdf and (any(f.lower().endswith(".pdf") for f in named) or re.search(r"pdf|피디에프", t) or not has_img):
        pdfs = [f for f in named if f.lower().endswith(".pdf")] or [f for f in files if f.lower().endswith(".pdf")][:1]
        return {"action": "split", "files": pdfs, "format": "png" if h["fmt"] == "png" else "jpg"}
    if h["fmt"] in IMG_FMT and has_img and not any(k in t for k in ["묶", "합쳐", "합치", "모아", "하나로"]):
        imgs = [f for f in named if Path(f).suffix.lower() in fconv.IMG_EXT]
        return {"action": "imgconv", "files": imgs or IMG_GLOBS, "target": h["fmt"]}

    if any(k in t for k in ["쪼개", "나눠", "분리", "이미지로", "사진으로"]) and \
            any(f.lower().endswith(".pdf") for f in files):
        pdfs = named or [f for f in files if f.lower().endswith(".pdf")][:1]
        return {"action": "split", "files": pdfs, "format": "png" if "png" in t else "jpg"}

    if any(k in t for k in ["묶", "합쳐", "모아", "하나로"]) or (not named and fmt in {"pdf", "pptx", "docx", "zip"}):
        plan = {"action": "bundle", "files": named or IMG_GLOBS, "out": f"묶음.{fmt or 'pdf'}",
                "sort": "time" if any(k in t for k in ["시간", "찍은", "날짜"]) else "name"}
        if any(k in t for k in ["용량", "작게", "가볍"]): plan.update(quality=60, max_size=1500)
        if any(k in t for k in ["고화질", "원본"]): plan.update(quality=95, max_size=0)
        n = re.search(r"(\d+)\s*장씩|페이지[당에]\s*(\d+)", t)
        if n: plan["per_page"] = int(n.group(1) or n.group(2))
        return plan

    if named and fmt:
        return {"action": "convert", "files": named, "target": fmt}
    return {"action": "unknown", "reason": "파일 이름이나 원하는 형식을 같이 말해주세요"}


# ───────── 계획 검사 (AI가 이상한 거 못 하게) ─────────
def resolve(patterns, files):
    out = []
    for p in patterns:
        hits = [f for f in files if fnmatch.fnmatch(f, p)] if any(c in p for c in "*?[") else \
               [f for f in files if f == p]
        out += [h for h in hits if h not in out]
    return sorted(out, key=fconv.natural_key)

def check(plan, files, allow_ocr=False):
    act = plan.get("action")
    if act not in {"bundle", "convert", "split", "imgconv"} | ({"ocr"} if allow_ocr else set()):
        raise ValueError(plan.get("reason", "처리할 수 없는 요청"))
    real = resolve(plan.get("files") or [], files)
    if not real:
        raise ValueError(f"해당하는 파일이 없음: {plan.get('files')}")
    plan["files"] = real
    if act == "convert":
        tgt = str(plan.get("target", "")).lower().lstrip(".")
        plan["target"] = tgt
        plan["files"] = [f for f in real if Path(f).suffix.lower().lstrip(".") != tgt]
        if not plan["files"]:
            raise ValueError("이미 그 형식이야")
    if act == "imgconv":
        tgt = {"jpeg": "jpg"}.get(str(plan.get("target", "")).lower().lstrip("."), str(plan.get("target", "")).lower().lstrip("."))
        if tgt not in IMG_FMT:
            raise ValueError("사진은 JPG·PNG·WEBP로 바꿀 수 있어요")
        plan["target"] = tgt
        plan["files"] = [f for f in real if Path(f).suffix.lower() in fconv.IMG_EXT
                         and Path(f).suffix.lower().lstrip(".").replace("jpeg", "jpg") != tgt]
        if not plan["files"]:
            raise ValueError(f"이미 전부 {tgt.upper()}예요")
    if act == "ocr":
        plan["files"] = [f for f in real if Path(f).suffix.lower() in fconv.IMG_EXT | {".pdf"}]
        tgt = str(plan.get("target") or "docx").lower().lstrip(".")
        plan["target"] = tgt if tgt in {"docx", "txt", "md"} else "docx"
        if not plan["files"]:
            raise ValueError("글자를 뽑을 사진이나 PDF가 없음")
    if act == "bundle":
        out = Path(plan.get("out") or "묶음.pdf").name             # 폴더 밖으로 못 나가게
        if Path(out).suffix.lower() not in {".pdf", ".docx", ".pptx", ".zip"}:
            out = Path(out).stem + ".pdf"
        plan["out"] = out
        plan["files"] = [f for f in real if Path(f).suffix.lower() in fconv.IMG_EXT]
        if not plan["files"]:
            raise ValueError("묶을 이미지가 없음")
    return plan

DOC_NAME = {"docx": "Word 문서", "pdf": "PDF", "md": "마크다운", "html": "웹페이지", "txt": "텍스트",
            "odt": "ODT 문서", "epub": "전자책(EPUB)"}

def describe(p):
    n = len(p["files"])
    head = ", ".join(p["files"][:3]) + (f" 외 {n-3}개" if n > 3 else "")
    if p["action"] == "bundle":
        extra = []
        if p.get("sort") == "time": extra.append("찍은 시간순")
        if int(p.get("per_page", 1)) > 1: extra.append(f"한 쪽에 {p['per_page']}장")
        if int(p.get("quality", 80)) < 80: extra.append("용량 작게")
        if int(p.get("quality", 80)) > 90: extra.append("원본 화질")
        return f"사진 {n}장 ({head})\n→ {p['out']} 한 파일로 합치기" + (f"\n[{', '.join(extra)}]" if extra else "")
    if p["action"] == "convert":
        return f"문서 {n}개 ({head})\n→ {DOC_NAME.get(p['target'], p['target'])}로 바꾸기"
    if p["action"] == "imgconv":
        return f"사진 {n}장 ({head})\n→ {p['target'].upper()}로 바꾸기"
    if p["action"] == "ocr":
        return f"{head}\n→ 글자를 뽑아서 {DOC_NAME.get(p['target'], p['target'])}로 (AI로 전송)"
    return f"{head}\n→ 페이지별 사진 (폴더)"


# ───────── 실행 ─────────
def run(p):
    if p["action"] == "bundle":
        fconv.bundle(p["files"], p["out"], p.get("sort", "name"), int(p.get("quality", 80)),
                     int(p.get("max_size", 2000)), int(p.get("per_page", 1)))
    elif p["action"] == "convert":
        for f in p["files"]:
            fconv.convert(f, p["target"])
    elif p["action"] == "imgconv":
        for f in p["files"]:
            fconv.convert_image(f, p["target"])
    elif p["action"] == "split":
        for f in p["files"]:
            fconv.split(f, p.get("format", "jpg"))

def handle(text, yes=False):
    files = sorted(f for f in os.listdir(".") if os.path.isfile(f))
    try:
        plan, who = ask_ai(text, files), "AI"
    except Exception:
        plan, who = ask_rules(text, files), "규칙"
    try:
        plan = check(plan, files)
    except ValueError as e:
        print(f"  ✗ {e}"); return
    print(f"  [{who}] {describe(plan)}")
    if not yes and input("  진행할까? (y/n) ").strip().lower() not in {"y", "ㅇ", "yes", ""}:
        print("  취소"); return
    try:
        run(plan)
    except SystemExit as e:
        print(f"  ✗ {e}")
    except Exception as e:
        print(f"  ✗ 실패: {e}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("request", nargs="*")
    ap.add_argument("-d", "--dir", default=".")
    ap.add_argument("-y", "--yes", action="store_true", help="확인 없이 바로 실행")
    a = ap.parse_args()
    os.chdir(os.path.expanduser(a.dir))
    if a.request:
        handle(" ".join(a.request), a.yes); return
    print(f"📂 {os.getcwd()}  (종료: q)")
    while True:
        try:
            t = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if t in {"q", "quit", "종료"}: break
        if t: handle(t, a.yes)

if __name__ == "__main__":
    main()
