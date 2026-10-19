"""Task 15：取代舊版、首頁一張卡、全站連結（最後一個 task 才會綠）。"""
import re
import subprocess
from pathlib import Path


def test_old_versions_gone(root):
    flow = root.parent
    assert root.name == 'entry-animation'
    assert not any((flow / n).exists() for n in ['entry-animation-2c', 'entry-animation-v2', 'entry-animation-v2a', 'entry-animation-v2b'])
    assert (root / 'README.md').exists() and (root / 'build' / 'README.md').exists()


def test_hub_single_card(root):
    h = (root.parents[1] / 'index.html').read_text(encoding='utf-8')
    assert h.count('flow/entry-animation/index.html') == 1 and 'entry-animation-v2' not in h and '進場動線 · 2c' in h


def test_no_dangling_links(root):   # 掃 taipei-dome 下所有 html 的相對 href/src/fetch，檔案都要存在
    dome = root.parents[1]
    missing = []
    for html in dome.rglob('*.html'):
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
    repo = root.parents[3]   # playground/
    assert (repo / '.git').exists()
    r = subprocess.run(['git', 'grep', '-n', 'entry-animation-v2', '--', 'design-explorations'], capture_output=True, text=True, cwd=repo)
    assert r.returncode == 1 and r.stdout == '', r.stdout[:500]
