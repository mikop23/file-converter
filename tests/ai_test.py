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
]
ok = 0
for text, act, test in cases:
    t0 = time.time()
    try:
        raw = fai.ask_ai(text, files, "local", localai.API)
        plan = fai.check(dict(raw), files)
        good = plan["action"] == act and test(plan)
    except Exception as e:
        raw, good = repr(e), False
    ok += good
    print(f"{'O' if good else 'X'}  {time.time() - t0:4.1f}s  {text}\n      AI: {raw}")
print(f"\n결과: {ok}/{len(cases)} 맞음")
