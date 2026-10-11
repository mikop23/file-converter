import zipfile
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
IN=Path('/tmp/claude-0/-home-claude-file-converter/601aa121-f574-5624-9e20-119b74fe9815/scratchpad/web/in'); DL=Path('/tmp/claude-0/-home-claude-file-converter/601aa121-f574-5624-9e20-119b74fe9815/scratchpad/web/rot'); res=[]
def ok(n,c,x=""): res.append(c); print(("O " if c else "X ")+n, x)
with sync_playwright() as p:
    b=p.chromium.launch()
    ctx=b.new_context(viewport={"width":390,"height":844}, device_scale_factor=2, accept_downloads=True, has_touch=True, is_mobile=True)
    pg=ctx.new_page(); errs=[]
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8765/index.html"); pg.wait_for_function("window.__fconv")
    pg.set_input_files("#pick", [str(IN/"사진2.jpg"), str(IN/"사진3.jpg"), str(IN/"메모.md")]); pg.wait_for_timeout(400)
    ok("사진에만 돌리기 버튼", pg.locator("#list li .rot:visible").count()==2, str(pg.locator("#list li .rot:visible").count()))
    pg.locator("#list li .rot").nth(0).tap()                      # 사진2: 90°
    pg.locator("#list li .rot").nth(1).tap(); pg.locator("#list li .rot").nth(1).tap()   # 사진3: 180°
    tr=pg.locator("#list li .thumb").nth(0).get_attribute("style")
    ok("썸네일도 돌아감", "rotate(90deg)" in (tr or ""), tr)
    pg.wait_for_timeout(400); pg.screenshot(path=str(DL/"mobile.png"), full_page=False)
    ok("폰 안내 문구", "▲▼" in pg.inner_text("#trayTip"), pg.inner_text("#trayTip"))
    xs=[round(pg.locator("#list li .rm").nth(i).bounding_box()["x"]) for i in range(3)]
    ok("× 위치 맞춤", len(set(xs))==1, str(xs))
    def grab(sel):
        with pg.expect_download() as d: pg.locator(sel).tap()
        f=DL/d.value.suggested_filename; d.value.save_as(f); return f
    pdf=grab("[data-bundle=pdf]")
    import pypdfium2 as pdfium
    doc=pdfium.PdfDocument(str(pdf)); sz=[tuple(round(x) for x in doc[i].get_size()) for i in range(len(doc))]
    ok("PDF: 90° 돌린 사진은 세로, 180°는 가로", sz[0][1]>sz[0][0] and sz[1][0]>sz[1][1], str(sz))
    pg.wait_for_function("!window.__fconv.state.busy")
    with pg.expect_download() as d1: pg.locator("[data-imgconv=png]").tap()
    a=DL/d1.value.suggested_filename; d1.value.save_as(a)
    im=Image.open(a)
    ok("형식 바꾸기에도 반영 (2400×1600 → 1600×2400)", im.size==(1600,2400), f"{a.name} {im.size}")
    # 사진3 180°: 원본 왼쪽 위 흰 사각형이 오른쪽 아래로
    pg.wait_for_function("!window.__fconv.state.busy"); pg.wait_for_timeout(500)
    files=sorted(DL.glob("사진3*.png"))
    if files:
        im3=Image.open(files[0]).convert("RGB"); ok("180° 픽셀 확인 (흰 사각형이 오른쪽 아래)", im3.getpixel((2350,1550))==(255,255,255) and im3.getpixel((50,50))!=(255,255,255))
    sw=pg.evaluate("document.documentElement.scrollWidth"); ok("폰 화면 가로 넘침 없음", sw<=390, str(sw))
    ok("오류 없음", not errs, str(errs))
    b.close()
print(f"{sum(res)}/{len(res)} 통과")
