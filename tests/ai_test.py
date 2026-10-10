"""진짜 AI 모델로 '말 알아듣기' 테스트 (GitHub 빌드에서 실행)"""
import sys, time
sys.path.insert(0, ".")
import fai, localai

files = ["IMG_0001.jpg", "IMG_0002.jpg", "IMG_0010.jpg", "스크린샷.png", "보고서.docx",
         "발표자료.pptx", "스캔본.pdf", "메모.md"]
cases = [
    ("사진들 찍은 순서대로 pdf로 묶어줘", "bundle", lambda p: p["out"].endswith(".pdf") and p.get("sort") == "time"),
    ("이미지 전부 피피티로 만들어", "bundle", lambda p: p["out"].endswith(".pptx")),
    ("사진 워드에 한 페이지 2장씩 넣어줘", "bundle", lambda p: p["out"].endswith(".docx") and int(p.get("per_page", 1)) == 2),
    ("사진 용량 작게 해서 압축파일로", "bundle", lambda p: p["out"].endswith(".zip")),
    ("보고서.docx pdf로 바꿔줘", "convert", lambda p: p["target"] == "pdf" and p["files"] == ["보고서.docx"]),
    ("발표자료 pdf로", "convert", lambda p: p["target"] == "pdf" and p["files"] == ["발표자료.pptx"]),
    ("메모.md 워드 파일로 변환", "convert", lambda p: p["target"] == "docx"),
    ("스캔본 페이지별로 이미지로 쪼개줘", "split", lambda p: p["files"] == ["스캔본.pdf"]),
    ("사진 다 합쳐서 하나의 파일로", "bundle", lambda p: len(p["files"]) == 4),
    ("IMG_0001이랑 IMG_0002만 pdf로 묶어", "bundle", lambda p: p["files"] == ["IMG_0001.jpg", "IMG_0002.jpg"]),
    ("스캔본.pdf를 워드로", "convert", lambda p: p["target"] == "docx" and p["files"] == ["스캔본.pdf"]),
    ("오늘 날씨 어때", "unknown", lambda p: True),
]
ok = 0
for text, act, test in cases:
    t0 = time.time()
    try:
        raw = fai.ask_ai(text, files, "local", localai.API)
        if act == "unknown":
            try:
                fai.check(fai.fix_plan(dict(raw), text, files), files); good = False
            except ValueError:
                good = True
        else:
            plan = fai.check(fai.fix_plan(dict(raw), text, files), files)
            good = plan["action"] == act and test(plan)
    except Exception as e:
        raw, good = repr(e), False
    ok += good
    line = f"{time.time() - t0:4.1f}s  {text}  →  AI: {raw}".replace("\n", " ")
    print(f"{'O' if good else 'X'}  {line}")
    if not good:
        print(f"::warning::틀림  {line}")
print(f"\n결과: {ok}/{len(cases)} 맞음")
print(f"::notice::AI 테스트 결과 {ok}/{len(cases)} 맞음")
