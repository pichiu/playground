"""發行（版本 3.1）：首頁有版本 3.1 卡、版本 3 卡保留、2c 與版本 3 的資料與建置不動、全站連結、README 在、追蹤檔可重現。"""
import hashlib
import json
import re
import subprocess
import sys

import inline

BASE_2C = 'd9af8c5'   # 2c 最後一次刻意改資料與建置（10/23 code review：分兩出口的列、保留席由資料提供）；之後 2c 不動


def test_readmes_present(root):
    assert root.name == 'entry-animation-v3.1'
    assert (root / 'README.md').exists() and (root / 'build' / 'README.md').exists()
    text = (root / 'README.md').read_text(encoding='utf-8')
    assert '版本 3.1' in text and '集合區' in text and '../entry-animation/' in text and '../entry-animation-v3-archive/' in text and '尚需現場確認' in text


def test_hub_has_only_v31_card(root):                   # 11/9 定案：總覽頁只有版本 3.1 卡片（版本 3 與 2c 都拿掉）
    h = (root.parents[1] / 'index.html').read_text(encoding='utf-8')
    assert h.count('flow/entry-animation-v3.1/index.html') == 1 and 'flow/entry-animation-v3/index.html' not in h and 'flow/entry-animation/index.html' not in h
    assert '進場動線 · 版本 3.1（定案）' in h and '進場動線 · 2c' not in h and '進場動線 · 版本 3（定案）' not in h


def test_v3_urls_redirect_to_v31(root):                  # 版本 3 網址已公告：八頁都直接轉到版本 3.1 同一頁（保留網址參數）
    v3 = root.parent / 'entry-animation-v3'
    for name in ['index.html', 'console.html', 'me.html', 'score.html', 'handout.html', 'captain.html', 'exit.html', 'diorama.html']:
        h = (v3 / name).read_text(encoding='utf-8')
        assert f"url=../entry-animation-v3.1/{name}" in h and f"location.replace('../entry-animation-v3.1/{name}'+location.search+location.hash)" in h, name
        assert (root / name).exists(), name


def test_v3_redirect_in_browser(root, browser):           # 實際在瀏覽器開版本 3 的我的路，落在版本 3.1 同一人
    import socket
    import time
    import urllib.request
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    proc = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1'], cwd=root.parent,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f'http://127.0.0.1:{port}/'
        for _ in range(50):
            try:
                urllib.request.urlopen(base + 'entry-animation-v3/me.html', timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        ctx = browser.new_context(viewport={'width': 400, 'height': 800})
        pg = ctx.new_page()
        pg.goto(base + 'entry-animation-v3/me.html?id=1-28', wait_until='load')
        pg.wait_for_url('**/entry-animation-v3.1/me.html?id=1-28', timeout=10000)
        pg.wait_for_function("document.querySelector('#lie') && document.querySelector('#lie').value === '1'", timeout=20000)
        ctx.close()
    finally:
        proc.terminate()


def test_v3_archive_data_untouched(root):               # 舊版 3 留存在 archive：資料與建置與 main 上的 entry-animation-v3 逐位元相同（只動頁面停用提示、README 與測試）
    repo = root.parents[3]
    arc = root.parent / 'entry-animation-v3-archive'
    files = ['data.json', 'seats.csv'] + [f'build/{p.name}' for p in (arc / 'build').iterdir() if p.is_file() and p.suffix in ('.py', '.json', '.html')]
    for f in files:
        old = subprocess.run(['git', 'show', f'origin/main:design-explorations/taipei-dome/flow/entry-animation-v3/{f}'], capture_output=True, cwd=repo)
        if old.returncode == 0:
            assert old.stdout == (arc / f).read_bytes(), f'{f} 與 main 的版本 3 不同'



def test_2c_data_and_build_untouched(root):   # 2c 只動 README、頁面顯示（10/23 企劃：時間改百分比、拿掉時刻）與頁面測試；資料與建置不動
    repo = root.parents[3]
    r = subprocess.run(['git', 'diff', '--name-only', BASE_2C, '--', 'design-explorations/taipei-dome/flow/entry-animation/'],
                       capture_output=True, text=True, cwd=repo)
    d = 'design-explorations/taipei-dome/flow/entry-animation/'
    changed = [f[len(d):] for f in r.stdout.split()]
    frozen = [f for f in changed if f in ('data.json', 'seats.csv') or (f.startswith('build/') and not f.startswith('build/tests/'))]
    assert not frozen, frozen
    assert 'entry-animation-v3' in (root.parent / 'entry-animation' / 'README.md').read_text(encoding='utf-8')


def test_no_dangling_links(root):   # 掃 taipei-dome 下所有 html 的相對 href/src/fetch，檔案都要存在
    dome = root.parents[1]
    missing = []
    for html in dome.rglob('*.html'):
        if html.parent.name == 'src':
            continue
        text = html.read_text(encoding='utf-8', errors='ignore')
        refs = re.findall(r'''(?:href|src)=["']([^"'#?]+)''', text) + re.findall(r'''fetch\(["']([^"'?]+)["']''', text)
        for ref in refs:
            if re.match(r'^(https?:|data:|mailto:|javascript:|//)', ref) or not ref.strip() or '${' in ref:
                continue
            if not (html.parent / ref).resolve().exists():
                missing.append(f'{html.relative_to(dome)} → {ref}')
    assert not missing, missing


def test_no_2c_wording_in_pages(root):
    for name in ['index.html', 'console.html', 'me.html', 'score.html', 'handout.html', 'captain.html', 'exit.html', 'diorama.html', 'core.js']:
        text = (root / name).read_text(encoding='utf-8')
        text = text.replace('舊版 <a href="../entry-animation/index.html">2c</a> 已停用', '')
        text = text.replace('2c 藍衣集結區', '').replace('與 2c（<a href="../entry-animation/index.html">對照</a>）', '')   # 版本 3.1 總覽：說明集合區的來源與對照連結
        assert not re.search(r'(?<![\w#])2c(?!\w)', text), name


def test_tracked_outputs_match_pipeline(root, pipeline):
    """追蹤的 data.json / seats.csv 必須就是重跑管線的結果（逐位元相同）。"""
    tmp, _ = pipeline
    for name in ['data.json', 'seats.csv']:
        assert hashlib.sha256((tmp / name).read_bytes()).hexdigest() == hashlib.sha256((root / name).read_bytes()).hexdigest(), name


def test_diorama_matches_src(root):
    """追蹤的 diorama.html 必須就是 build/diorama.src.html 以 inline.py 重新產生的結果（逐位元相同）。"""
    want = hashlib.sha256(inline.pages_html().encode('utf-8')).hexdigest()
    assert hashlib.sha256((root / 'diorama.html').read_bytes()).hexdigest() == want, 'diorama.html 不是最新的：請在 build/ 執行 python3 -I inline.py'


def test_diorama_copied_engine_matches_core(root):
    """src 裡「原樣複製自 core.js」的引擎函式（artifact 版沒有 core.js 可用）必須仍逐字存在於 core.js。"""
    core = (root / 'core.js').read_text(encoding='utf-8')
    src = (root / 'build' / 'diorama.src.html').read_text(encoding='utf-8').split('\n')
    for head in ('const pairs=', 'function bounds(', 'function pos(', 'function state(', 'function counts('):
        line = next(l for l in src if l.startswith(head))
        assert line in core, f'diorama.src.html 的 {head} 和 core.js 不同，請重新複製'


DOME_DATA_TAG = '<script type="application/json" id="dome-data">'


def _embedded(html):
    assert html.count(DOME_DATA_TAG) == 1                        # 資料只內嵌一次
    return html.partition(DOME_DATA_TAG)[2].partition('</script>')[0]


def test_diorama_artifact_build(root):
    """artifact 版：data.json 原文內嵌（解析回來相同）。"""
    text = (root / 'data.json').read_text(encoding='utf-8')
    blob = _embedded(inline.artifact_html(str(root / 'data.json')))
    assert '<' not in blob and json.loads(blob) == json.loads(text)


def test_diorama_artifact_escapes_script_breakers(tmp_path):
    """含 "</script>"、"<!--<script" 的字串不能讓內嵌的 script 提早結束。"""
    data = {'note': '</script><!--<script>x</script>', 'n': [1, 2]}
    p = tmp_path / 'd.json'
    p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    html = inline.artifact_html(str(p))
    assert '<!--' not in _embedded(html) and json.loads(_embedded(html)) == data


def test_hub_v31_card_copy_current(root):                # 版本 3.1 卡：寫集合區、不寫門前隊伍
    h = (root.parents[1] / 'index.html').read_text(encoding='utf-8')
    i = h.index('flow/entry-animation-v3.1/index.html')
    card = h[i:h.index('</a>', i)]
    assert '集合區' in card and '門前隊伍' not in card and '現場確認' in card
