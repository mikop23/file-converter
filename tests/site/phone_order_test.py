from pathlib import Path
from playwright.sync_api import sync_playwright
IN=Path('/tmp/claude-0/-home-claude-file-converter/601aa121-f574-5624-9e20-119b74fe9815/scratchpad/web/in'); res=[]
def ok(n,c,x=""): res.append(c); print(("O " if c else "X ")+n, x)
with sync_playwright() as p:
    b=p.chromium.launch(); errs=[]
    m=b.new_context(viewport={"width":390,"height":844}, device_scale_factor=2, has_touch=True, is_mobile=True, accept_downloads=True)
    pg=m.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8765/index.html"); pg.wait_for_function("window.__fconv")
    pg.set_input_files("#pick", [str(IN/"사진1.jpg"), str(IN/"사진2.jpg"), str(IN/"사진3.jpg")]); pg.wait_for_timeout(300)
    names=lambda: [pg.locator("#list li .fname").nth(i).inner_text() for i in range(3)]
    ok("폰: ▲▼ 보임", pg.locator("#list .mv").count()==3)
    ok("맨 위 ▲ / 맨 아래 ▼ 꺼짐", pg.locator("#list li").nth(0).locator(".mv button").nth(0).is_disabled() and pg.locator("#list li").nth(2).locator(".mv button").nth(1).is_disabled())
    pg.locator("#list li").nth(2).locator(".mv button").nth(0).tap()     # 사진3 위로
    ok("▲ 누르면 위로", names()==["사진1.jpg","사진3.jpg","사진2.jpg"], str(names()))
    pg.locator("#list li").nth(0).locator(".mv button").nth(1).tap()     # 사진1 아래로
    ok("▼ 누르면 아래로", names()==["사진3.jpg","사진1.jpg","사진2.jpg"], str(names()))
    pg.locator("#list li").nth(0).locator(".rot").tap()                 # 돌린 것도 순서 바뀌어도 유지
    pg.locator("#list li").nth(0).locator(".mv button").nth(1).tap()
    ok("돌린 각도는 따라감", "rotate(90deg)" in (pg.locator("#list li").nth(1).locator(".thumb").get_attribute("style") or ""))
    with pg.expect_download() as d: pg.locator("[data-bundle=zip]").tap()
    import zipfile; f=Path('/tmp/claude-0/-home-claude-file-converter/601aa121-f574-5624-9e20-119b74fe9815/scratchpad/web/rot')/d.value.suggested_filename; d.value.save_as(f)
    ok("ZIP이 바꾼 순서대로", [n.split('_',1)[1] for n in zipfile.ZipFile(f).namelist()]==["사진1.jpg","사진3.jpg","사진2.jpg"], str(zipfile.ZipFile(f).namelist()))
    sw=pg.evaluate("document.documentElement.scrollWidth"); ok("가로 넘침 없음", sw<=390, str(sw))
    ok("안내 문구", "▲▼" in pg.inner_text("#trayTip"))
    pg.screenshot(path='/tmp/claude-0/-home-claude-file-converter/601aa121-f574-5624-9e20-119b74fe9815/scratchpad/web/rot/mv.png', clip={"x":0,"y":280,"width":390,"height":380})
    d2=b.new_context(viewport={"width":1280,"height":900}); pd=d2.new_page(); pd.goto("http://127.0.0.1:8765/index.html"); pd.wait_for_function("window.__fconv")
    pd.set_input_files("#pick", [str(IN/"사진1.jpg")]); pd.wait_for_timeout(200)
    ok("PC 브라우저엔 ▲▼ 없음 (끌기 사용)", pd.locator("#list .mv").count()==0)
    ok("오류 없음", not errs, str(errs)); b.close()
print(f"{sum(res)}/{len(res)} 통과")
