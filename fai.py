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

def make_plan(text, files, model=None, api=None):
    """요청 → (검사된 계획, 'AI'|'규칙'). AI가 틀리면 규칙으로 한 번 더. 둘 다 실패 시 ValueError"""
    if model:
        try:
            return check(ask_ai(text, files, model, api), files), "AI"
        except Exception:
            pass
    return check(ask_rules(text, files), files), "규칙"

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
def ask_rules(text, files):
    t = text.lower()
    named = [f for f in files if f.lower() in t]
    rest = t
    for f in named: rest = rest.replace(f.lower(), " ")   # 파일명 속 확장자는 형식으로 안 봄
    fmt = next((f for f in ["pptx", "docx", "pdf", "zip", "html", "md", "txt", "epub", "odt", "png", "jpg"]
                if f in rest), None)
    alias = {"피피티": "pptx", "ppt": "pptx", "파워포인트": "pptx", "워드": "docx", "word": "docx",
             "압축": "zip", "마크다운": "md", "텍스트": "txt", "웹": "html", "pdf": "pdf", "피디에프": "pdf"}
    for k, v in alias.items():
        if k in rest and not fmt: fmt = v

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
    return {"action": "unknown", "reason": "파일 이름이나 원하는 형식을 같이 말해줘"}


# ───────── 계획 검사 (AI가 이상한 거 못 하게) ─────────
def resolve(patterns, files):
    out = []
    for p in patterns:
        hits = [f for f in files if fnmatch.fnmatch(f, p)] if any(c in p for c in "*?[") else \
               [f for f in files if f == p]
        out += [h for h in hits if h not in out]
    return sorted(out, key=fconv.natural_key)

def check(plan, files):
    act = plan.get("action")
    if act not in {"bundle", "convert", "split"}:
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
    if act == "bundle":
        out = Path(plan.get("out") or "묶음.pdf").name             # 폴더 밖으로 못 나가게
        if Path(out).suffix.lower() not in {".pdf", ".docx", ".pptx", ".zip"}:
            out = Path(out).stem + ".pdf"
        plan["out"] = out
        plan["files"] = [f for f in real if Path(f).suffix.lower() in fconv.IMG_EXT]
        if not plan["files"]:
            raise ValueError("묶을 이미지가 없음")
    return plan

def describe(p):
    n = len(p["files"])
    head = ", ".join(p["files"][:3]) + (f" 외 {n-3}개" if n > 3 else "")
    if p["action"] == "bundle":
        extra = []
        if p.get("sort") == "time": extra.append("찍은 시간순")
        if p.get("per_page", 1) > 1: extra.append(f"페이지당 {p['per_page']}장")
        if p.get("quality", 80) < 80: extra.append("용량 줄이기")
        return f"이미지 {n}장({head}) → {p['out']}" + (f"  [{', '.join(extra)}]" if extra else "")
    if p["action"] == "convert":
        return f"{head} → {p['target']} 변환"
    return f"{head} → 페이지별 {p.get('format','jpg')} 이미지"


# ───────── 실행 ─────────
def run(p):
    if p["action"] == "bundle":
        fconv.bundle(p["files"], p["out"], p.get("sort", "name"), int(p.get("quality", 80)),
                     int(p.get("max_size", 2000)), int(p.get("per_page", 1)))
    elif p["action"] == "convert":
        for f in p["files"]:
            fconv.convert(f, p["target"])
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
