"""Task 15：取代舊版、首頁一張卡、全站連結、追蹤檔可重現。

例外：`flow/entry-animation-v2/` 的連結已外傳（GitHub Pages），所以暫時原樣保留，首頁與 2c 的頁面都不連到它；
PR 正式合併、確認可改後再清（刪資料夾、把 test_v2_kept_verbatim_for_shared_link 改回「不存在」）。
"""
import hashlib
import re
import subprocess

PRE_REMOVAL = 'd634d19^'   # 刪舊版那個 commit 的前一個：暫存的 v2 資料夾以它為準
V2 = 'design-explorations/taipei-dome/flow/entry-animation-v2'


def _git(repo, *args):
    return subprocess.run(['git', *args], capture_output=True, cwd=repo)


def test_old_versions_gone(root):
    flow = root.parent
    assert root.name == 'entry-animation'
    assert not any((flow / n).exists() for n in ['entry-animation-2c', 'entry-animation-v2a', 'entry-animation-v2b'])
    assert (root / 'README.md').exists() and (root / 'build' / 'README.md').exists()


def test_v2_kept_verbatim_for_shared_link(root):
    """外傳連結要能用：v2 資料夾與刪除前一模一樣；另加 redesign/src/v1.html（版本 1 頁原樣），它的「版本 1／對照」切換才讀得到資料。"""
    repo = root.parents[3]
    v2 = root.parent / 'entry-animation-v2'
    assert (v2 / 'index.html').exists() and (v2 / 'redesign' / 'index.html').exists()
    r = _git(repo, 'diff', '--quiet', PRE_REMOVAL, '--', V2, f':!{V2}/redesign/src/*')
    assert r.returncode == 0, r.stderr.decode()[:500]
    want = _git(repo, 'show', f'{PRE_REMOVAL}:design-explorations/taipei-dome/flow/entry-animation/index.html').stdout
    assert want and (v2 / 'redesign' / 'src' / 'v1.html').read_bytes() == want


def test_hub_single_card(root):
    h = (root.parents[1] / 'index.html').read_text(encoding='utf-8')
    assert h.count('flow/entry-animation/index.html') == 1 and 'entry-animation-v2' not in h and '進場動線 · 2c' in h


def test_no_dangling_links(root):   # 掃 taipei-dome 下所有 html 的相對 href/src/fetch，檔案都要存在
    dome = root.parents[1]
    missing = []
    for html in dome.rglob('*.html'):
        if html.parent.name == 'src':   # redesign/src/*.html 只是資料來源（fetch 文字取內嵌 DATA），不是導覽頁
            continue
        text = html.read_text(encoding='utf-8', errors='ignore')
        refs = re.findall(r'''(?:href|src)=["']([^"'#?]+)''', text) + re.findall(r'''fetch\(["']([^"'?]+)["']''', text)
        for ref in refs:
            if re.match(r'^(https?:|data:|mailto:|javascript:|//)', ref) or not ref.strip() or '${' in ref:   # ${…} 是 JS 樣板字串
                continue
            target = (html.parent / ref).resolve()
            if not target.exists():
                missing.append(f'{html.relative_to(dome)} → {ref}')
    assert not missing, missing


def test_git_grep_clean(root):
    """2c 的頁面、程式與資料不得再提到舊資料夾；暫存的 v2 本身、測試、README 的註記除外。"""
    repo = root.parents[3]
    assert (repo / '.git').exists()
    r = _git(repo, 'grep', '-n', 'entry-animation-v2', '--', 'design-explorations/*.html', 'design-explorations/*.js', 'design-explorations/*.py',
             'design-explorations/*.json', 'design-explorations/*.csv', f':!{V2}/*', ':!*/tests/*')
    assert r.returncode == 1 and r.stdout == b'', r.stdout.decode()[:500]


def test_tracked_outputs_match_pipeline(root, pipeline):
    """追蹤的 data.json / seats.csv 必須就是重跑管線的結果（逐位元相同），改了規則沒重算會在這裡紅。"""
    tmp, _ = pipeline
    for name in ['data.json', 'seats.csv']:
        assert hashlib.sha256((tmp / name).read_bytes()).hexdigest() == hashlib.sha256((root / name).read_bytes()).hexdigest(), name
