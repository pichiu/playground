"""發行（版本 3.1）：首頁有版本 3.1 卡、版本 3 卡保留、2c 與版本 3 的資料與建置不動、全站連結、README 在、追蹤檔可重現。"""
import hashlib
import json
import re
import subprocess

import inline

BASE_2C = 'd9af8c5'   # 2c 最後一次刻意改資料與建置（10/23 code review：分兩出口的列、保留席由資料提供）；之後 2c 不動


def test_readmes_present(root):
    assert root.name == 'entry-animation-v3.1'
    assert (root / 'README.md').exists() and (root / 'build' / 'README.md').exists()
    text = (root / 'README.md').read_text(encoding='utf-8')
    assert '版本 3.1' in text and '集合區' in text and '../entry-animation/' in text and '../entry-animation-v3/' in text and '尚需現場確認' in text


def test_hub_has_v31_and_v3_cards(root):
    h = (root.parents[1] / 'index.html').read_text(encoding='utf-8')
    assert h.count('flow/entry-animation-v3.1/index.html') == 1 and h.count('flow/entry-animation-v3/index.html') == 1 and 'flow/entry-animation/index.html' not in h
    assert '進場動線 · 版本 3.1' in h and '進場動線 · 版本 3（定案）' in h and '進場動線 · 2c' not in h
    assert h.index('flow/entry-animation-v3.1/index.html') < h.index('flow/entry-animation-v3/index.html')


def test_v3_untouched(root):                             # 版本 3 保留作對照：整個資料夾不動（只在 git 有記錄時檢查）
    repo = root.parents[3]
    r = subprocess.run(['git', 'diff', '--name-only', 'HEAD', '--', 'design-explorations/taipei-dome/flow/entry-animation-v3/'], capture_output=True, text=True, cwd=repo)
    assert r.returncode == 0 and not r.stdout.strip(), r.stdout


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
