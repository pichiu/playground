"""Google Fonts 載不到或很慢時，七個頁面與 data.json 都不能被卡住（字型非阻塞載入）。"""
import re

import pytest

PAGES = ['index.html', 'console.html', 'me.html?id=1-28', 'score.html', 'handout.html', 'captain.html', 'exit.html']


def test_font_links_are_non_blocking(root):
    for name in [p.split('?')[0] for p in PAGES]:
        html = (root / name).read_text(encoding='utf-8')
        no_noscript = re.sub(r'<noscript>.*?</noscript>', '', html, flags=re.S)
        assert not re.search(r'<link[^>]+rel="stylesheet"[^>]+fonts\.googleapis', no_noscript), f'{name}: 同步字型 stylesheet 會擋住 core.js 與 data.json'
        assert re.search(r'<link rel="preload" as="style" href="https://fonts\.googleapis[^>]+onload="', html), name
        assert re.search(r'<noscript><link rel="stylesheet" href="https://fonts\.googleapis', html), name


@pytest.mark.parametrize('path', PAGES)
def test_ready_while_fonts_stall(server, browser, path):
    ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
    try:
        pg = ctx.new_page()
        pg.route(re.compile(r'fonts\.g(oogleapis|static)\.com'), lambda route: None)   # 永不回應，模擬字型 CDN 卡住
        pg.goto(server + path, wait_until='commit')
        pg.wait_for_function('window.__dome_ready === true', timeout=8000)
    finally:
        ctx.close()
