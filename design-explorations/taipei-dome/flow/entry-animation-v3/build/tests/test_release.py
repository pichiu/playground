"""發行：首頁兩張進場動線卡、2c 資料與建置不動、全站連結、README 在、追蹤檔可重現。"""
import hashlib
import json
import re
import subprocess

BASE_2C = 'd9af8c5'   # 2c 最後一次刻意改資料與建置（10/23 code review：分兩出口的列、保留席由資料提供）；之後 2c 不動


def test_readmes_present(root):
    assert root.name == 'entry-animation-v3'
    assert (root / 'README.md').exists() and (root / 'build' / 'README.md').exists()
    text = (root / 'README.md').read_text(encoding='utf-8')
    assert '版本 3' in text and '兩路' in text and '../entry-animation/' in text


def test_hub_has_v3_card(root):
    h = (root.parents[1] / 'index.html').read_text(encoding='utf-8')
    assert h.count('flow/entry-animation-v3/index.html') == 1 and h.count('flow/entry-animation/index.html') == 1
    assert '進場動線 · 版本 3' in h and '進場動線 · 2c' in h


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
        text = text.replace('../entry-animation/index.html">2c 總覽', '')
        assert not re.search(r'(?<![\w#])2c(?!\w)', text), name


def test_tracked_outputs_match_pipeline(root, pipeline):
    """追蹤的 data.json / seats.csv 必須就是重跑管線的結果（逐位元相同）。"""
    tmp, _ = pipeline
    for name in ['data.json', 'seats.csv']:
        assert hashlib.sha256((tmp / name).read_bytes()).hexdigest() == hashlib.sha256((root / name).read_bytes()).hexdigest(), name


def test_diorama_matches_src(root):
    """追蹤的 diorama.html 必須就是 build/diorama.src.html 以 inline.py 重新產生的結果（改了 src 忘了重跑就會失敗）。"""
    import inline
    assert inline.pages_html() == (root / 'diorama.html').read_text(encoding='utf-8')


def test_diorama_artifact_build(root, tmp_path):
    """artifact 版：資料剛好內嵌一次、"</" 已跳脫，解析回來和 data.json 相同。"""
    import inline
    html = inline.artifact_html(str(root / 'data.json'))
    i = html.index('<script type="application/json" id="dome-data">') + len('<script type="application/json" id="dome-data">')
    blob = html[i:html.index('</script>', i)]
    assert '</' not in blob and json.loads(blob) == json.loads((root / 'data.json').read_text(encoding='utf-8'))


def test_hub_v3_card_copy_current(root):                 # review：首頁卡不得留著不集結版本的說法
    h = (root.parents[1] / 'index.html').read_text(encoding='utf-8')
    i = h.index('flow/entry-animation-v3/index.html')
    card = h[i:h.index('</a>', i)]
    assert '沒有人停下來等' not in card and '18 秒' not in card and '門前' in card
