#!/usr/bin/env python3
"""inline.py：由 build/diorama.src.html 產生 3D 模型頁的兩種輸出。

  python3 -I inline.py                          頁面版：寫到 ../diorama.html。不內嵌資料，頁面用同資料夾
                                                core.js 的 Dome.load() 讀 data.json；補上 doctype／head／viewport 與基本 reset
  python3 -I inline.py --artifact OUT.html [DATA]
                                                claude.ai artifact 版：把 data.json（預設 ../data.json，build.py 已寫成一行）
                                                的每個 "<" 換成 \\u003c 後取代 __DATA__；平台發佈時會自己包外殼，所以不加 doctype

../diorama.html 是追蹤檔，改 src 後要重跑本腳本；tests/test_release.py 會檢查它和 src 重新產生的結果逐位元相同。
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # entry-animation-v3/
SRC = os.path.join(HERE, 'diorama.src.html')
PAGE = os.path.join(ROOT, 'diorama.html')
DATA = os.path.join(ROOT, 'data.json')
# 與 artifact 平台發佈時包上的外殼相同（charset、viewport-fit=cover、safe-area padding、reset）
HEAD = ('<!doctype html>\n<html lang="zh-Hant-TW">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
        '<link rel="icon" href="data:,">\n'                 # 和其他七頁一樣，避免瀏覽器去要 favicon.ico（404）
        '<style>:root{color-scheme:light;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
        'html{scroll-padding-top:env(safe-area-inset-top,0px)}body{margin:0;padding:0;font:14px -apple-system,BlinkMacSystemFont,sans-serif;background:#fff;color:#000}'
        'img{max-width:100%}[hidden]:not([hidden=until-found i]){display:none!important}</style>\n')
PAGES_NOTE = ('<!-- 由 build/diorama.src.html 以 `python3 -I build/inline.py` 產生；'
              '要改請改 src 再重新產生，不要直接改這個檔。資料讀同資料夾的 data.json。 -->\n')


USAGE = 'usage: python3 -I inline.py | python3 -I inline.py --artifact OUT.html [DATA]'


def read_src():
    with open(SRC, encoding='utf-8', newline='') as f:
        src = f.read()
    if src.count('__DATA__') != 1:
        sys.exit('diorama.src.html 必須剛好有一個 __DATA__')
    return src


def pages_html():
    src = read_src().replace('__DATA__', '')
    cut = src.index('</style>') + len('</style>')            # <title>、meta、主樣式放進 head，其餘是 body
    head, body = src[:cut], src[cut:]
    mark = '<script type="importmap">'
    if body.count(mark) != 1:
        sys.exit('找不到唯一的 importmap')
    body = body.replace(mark, '<script src="core.js"></script>\n' + mark)
    return HEAD + PAGES_NOTE + head.lstrip() + '\n</head>\n<body>\n' + body.strip() + '\n</body>\n</html>\n'


def embed_json(text):
    """JSON 文字放進 <script type="application/json">：每個 "<" 換成 \\u003c（JSON 裡 "<" 只會出現在字串內，JSON.parse 會還原），
    "</script>"、"<!--<script" 都不會讓 HTML parser 提早結束這個 script。"""
    return text.strip().replace('<', '\\u003c')


def artifact_html(data_path):
    with open(data_path, encoding='utf-8') as f:            # build.py 已用 separators=(',', ':') 寫成一行，不必重新序列化
        return read_src().replace('__DATA__', embed_json(f.read()))


def write(dst, out):
    with open(dst, 'w', encoding='utf-8', newline='') as f:   # 不轉換換行，產出和平台無關
        f.write(out)
    print(f'wrote {dst} {len(out.encode("utf-8")):,} bytes')


def main(argv):
    if not argv:
        write(PAGE, pages_html())
    elif argv[0] == '--artifact' and len(argv) in (2, 3):
        write(argv[1], artifact_html(argv[2] if len(argv) == 3 else DATA))
    else:
        print(USAGE, file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main(sys.argv[1:])
