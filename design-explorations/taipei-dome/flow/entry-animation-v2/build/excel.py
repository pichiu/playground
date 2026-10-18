"""產生「休息區座位_藍衣B2集結版」xlsx:以 10/17 修正版「組數」工作表為底,改寫每格人員、依大隊重設底色,
加區塊離座說明列與「集結區對照」工作表。只保留這兩張工作表(含原本的離座箭頭與第一～四出標示)。"""
import json, re, sys, os, shutil, zipfile, collections
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.dirname(__file__))
from xlsxgrid import load, seatmap, n2col, col2n

U, PLAN, NEWDATA, OUT = sys.argv[1:5]
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
RNS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
ET.register_namespace('', NS); ET.register_namespace('r', RNS)
q = lambda t: '{%s}%s' % (NS, t)
plan = json.load(open(PLAN)); data = json.load(open(NEWDATA))
persons = {p['id']: p for p in data['persons']}
files = {f['lie']: f for f in data['files']}
zones = plan['zones']

cells = load(U)
sm = seatmap(cells)
strs_root = ET.parse(f'{U}/xl/sharedStrings.xml').getroot()
STRS = [''.join(t.text or '' for t in si.iter(q('t'))) for si in strs_root.findall(q('si'))]

# ---------- 樣式 ----------
styles_txt = open(f'{U}/xl/styles.xml', encoding='utf-8').read()
xfs_block = re.search(r'(<cellXfs count=")(\d+)(">)(.*?)(</cellXfs>)', styles_txt, re.S)
xf_list = re.findall(r'<xf [^>]*?(?:/>|>.*?</xf>)', xfs_block.group(4), re.S)
fonts_block = re.search(r'(<fonts count=")(\d+)("[^>]*>)(.*?)(</fonts>)', styles_txt, re.S)
n_fonts = int(fonts_block.group(2))
DADUI_FILL = {1: 19, 2: 18, 3: 3, 4: 17, 5: 16, 6: 20, 7: 21, 8: 14, 9: 23}
new_xfs = []
def xf_with(base, **attrs):
    x = xf_list[base]
    for k, v in attrs.items():
        if re.search(r'\b%s="' % k, x): x = re.sub(r'\b%s="[^"]*"' % k, '%s="%s"' % (k, v), x)
        else: x = x.replace('<xf ', '<xf %s="%s" ' % (k, v), 1)
    if 'fillId' in attrs and 'applyFill' not in x: x = x.replace('<xf ', '<xf applyFill="1" ', 1)
    if 'fontId' in attrs and 'applyFont' not in x: x = x.replace('<xf ', '<xf applyFont="1" ', 1)
    key = x
    if key in new_xfs: return len(xf_list) + new_xfs.index(key)
    new_xfs.append(key); return len(xf_list) + len(new_xfs) - 1
BOLD_FONT = n_fonts
fonts_add = '<font><b/><sz val="11"/><name val="微軟正黑體"/><family val="2"/><charset val="136"/></font>'
NOTE_FONT = n_fonts + 1
fonts_add += '<font><sz val="11"/><name val="微軟正黑體"/><family val="2"/><charset val="136"/></font>'
XF_PLAIN = 148
WRAP = '<xf numFmtId="0" fontId="%d" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
new_xfs.append(WRAP % NOTE_FONT); XF_WRAP = len(xf_list) + len(new_xfs) - 1
new_xfs.append('<xf numFmtId="0" fontId="%d" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top"/></xf>' % NOTE_FONT); XF_NOTE = len(xf_list) + len(new_xfs) - 1
new_xfs.append('<xf numFmtId="0" fontId="%d" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top"/></xf>' % BOLD_FONT); XF_BOLD = len(xf_list) + len(new_xfs) - 1
DADUI_XF = {}
for d, f in DADUI_FILL.items():
    new_xfs.append('<xf numFmtId="0" fontId="%d" fillId="%d" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="top"/></xf>' % (NOTE_FONT, f))
    DADUI_XF[d] = len(xf_list) + len(new_xfs) - 1

# ---------- 組數工作表 ----------
tree = ET.parse(f'{U}/xl/worksheets/sheet8.xml'); root = tree.getroot()
sd = root.find(q('sheetData'))
rows = {int(r.get('r')): r for r in sd.findall(q('row'))}
def get_cell(r, c, create=True):
    row = rows.get(r)
    if row is None:
        if not create: return None
        row = ET.SubElement(sd, q('row'), r=str(r)); rows[r] = row
        sd[:] = sorted(sd, key=lambda e: int(e.get('r')))
    ref = n2col(c) + str(r)
    for ce in row.findall(q('c')):
        if ce.get('r') == ref: return ce
    if not create: return None
    ce = ET.Element(q('c'), r=ref)
    kids = list(row); idx = len(kids)
    for k, e in enumerate(kids):
        m = re.match(r'([A-Z]+)', e.get('r'))
        if col2n(m.group(1)) > c: idx = k; break
    row.insert(idx, ce)
    return ce
def set_str(ce, text, style=None):
    for ch in list(ce): ce.remove(ch)
    for a in ('t',): ce.attrib.pop(a, None)
    if style is not None: ce.set('s', str(style))
    if text is None or text == '': return
    ce.set('t', 'inlineStr')
    is_ = ET.SubElement(ce, q('is')); t = ET.SubElement(is_, q('t')); t.text = text
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

# 共用字串一律改成 inline,才能丟掉 sharedStrings
for row in sd.findall(q('row')):
    for ce in row.findall(q('c')):
        if ce.get('t') == 's':
            v = ce.find(q('v')).text; set_str(ce, STRS[int(v)])

new_who = {(s['sec'], s['pai'], s['no']): pid for pid, s in plan['seats'].items()}
changed = 0
for key, info in sm.items():
    old = info['who'] if info['who'] and re.fullmatch(r'\d+-\d+', info['who']) else None
    new = new_who.get(key)
    if not old and not new: continue
    ce = get_cell(info['r'], info['c'])
    base = int(ce.get('s') or XF_PLAIN)
    if new:
        fid = DADUI_FILL[(int(new.split('-')[0]) - 1) // 6 + 1]
        set_str(ce, new, xf_with(base, fillId=fid))
        nc = get_cell(info['r'] - 1, info['c'], create=False)      # 上方座位號碼格同色
        if nc is not None and nc.get('s'): nc.set('s', str(xf_with(int(nc.get('s')), fillId=fid)))
    else:
        set_str(ce, None, xf_with(base, fillId=0))
    changed += (old != new)
print('改寫人員格', changed)

# 區段標題列:找每區的欄
heads = sorted((c, v) for (r, c), (v, s) in cells.items() if r == 2 and v and re.match(r'\d{3}', v))
SEC_COL = {v[:3]: c - 1 for c, v in heads}

WAVE = {1: '第一先出', 2: '第二先出', 3: '第三先出', 4: '第四出'}
CIRC = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'
def zlabel(z):
    return '集結區 1' if z == 'P1' else zones[z]['label'] + (' (樓梯)' if z == 'STAIR' else '')
# 每個區塊(含 L/R 半區)依離座順序列出各列
segs = collections.defaultdict(list)
for f in data['files']:
    for b in f['blocks']:
        segs[b['block']].append((persons[f['order'][0]]['t']['leave'] if b == f['blocks'][0] else
                                 min(persons[pid]['t']['leave'] for pid in f['order'] if persons[pid]['block'] == b['block']), f, b))
SIDE = {'S': '往南側走道', 'N': '往北側走道'}
COL_OFF = {'L': 0, 'R': 13, '': 0}
for blk, lst in segs.items():
    lst.sort(key=lambda x: x[0])
    sec = blk[:3]; half = blk[3:].replace('M', '')
    b0 = lst[0][2]; col = SEC_COL[sec] + COL_OFF[half]
    set_str(get_cell(36, col), '%s 鏈%s %s出 %s' % (blk.replace('M', ''), b0['chain'], SIDE[b0['exitSide']], WAVE[b0['exitWave']]), XF_BOLD)
    for k, (t, f, b) in enumerate(lst):
        lifo = f['direction'].startswith('離座 頭')
        set_str(get_cell(37 + k, col), '%s %d列 大隊%d%s %d人→%s(%s)' % (CIRC[k], f['lie'], f['dadui'], f['costume'], b['n'], zlabel(f['assembly']),
                                                                      '排1先' if lifo else '排大先'), DADUI_XF[f['dadui']])
ce = get_cell(47, 2)
set_str(ce, '版本 2・藍衣 B2 集結版(2026-10-18):表格版面沿用 10/17 修正版;座位、區塊、離座箭頭與第一～四出都沿用版本 1(10/18 座位),只重排每一列坐哪一段;141L 改走鏈 B,讓三條鏈長度接近。'
            '底色 = 大隊(同原表)。第 36 列起為各區塊的離座順序與集結區;集結區說明見「集結區對照」工作表。', XF_BOLD)
ce = get_cell(48, 2)
set_str(ce, '集結區名稱:B2 = 集結區 1(大隊 1 三白三藍,不變)、藍 2·3、藍 4·5、藍 6·7、藍 8·9;'
            'B1 = 白 2(樓梯)、白 3、白 4·5、白 6·7、白 8·9。名稱就是「衣色＋大隊」,志工看名稱就知道自己去哪。', XF_NOTE)
# 拿掉 printerSettings 參照
ps = root.find(q('pageSetup'))
if ps is not None: ps.attrib.pop('{%s}id' % RNS, None)
sv = root.find(q('sheetViews')).find(q('sheetView')); sv.set('tabSelected', '1')
sheet1 = ET.tostring(root, encoding='unicode', xml_declaration=False)
_all = xf_list + new_xfs
def _plain(i):
    x = _all[i]; f = re.search(r'fillId="(\d+)"', x); b = re.search(r'borderId="(\d+)"', x)
    return (not f or f.group(1) == '0') and (not b or b.group(1) == '0')
_before = len(sheet1)
sheet1 = re.sub(r'<c r="[A-Z]+\d+"(?: s="(\d+)")? */>', lambda m: '' if _plain(int(m.group(1) or 0)) else m.group(0), sheet1)
print('空白格精簡', _before, '→', len(sheet1))
sheet1 = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + sheet1

# ---------- 集結區對照 ----------
ZONE_ROWS = [
    ('P1', 'B2・樓梯下到 6口 之間(頭朝 6口)', [1, 2, 3, 4, 5, 6], '大隊 1 白衣三列＋藍衣三列(不變)'),
    ('P2', 'B2・6口 南側第一區(死巷)', [10, 11, 12, 16, 17, 18], '大隊 2 藍衣(靠場內側)＋大隊 3 藍衣'),
    ('P3', 'B2・6口 南側第二區(死巷)', [22, 23, 24, 28, 29, 30], '大隊 4 藍衣(靠場內側)＋大隊 5 藍衣'),
    ('P4', 'B2・6口 南側第三區(死巷)', [34, 35, 36, 40, 41, 42], '大隊 6 藍衣(靠場內側)＋大隊 7 藍衣'),
    ('P5', 'B2・6口 南側最裡面(死巷)', [46, 47, 48, 52, 53, 54], '大隊 8 藍衣(靠場內側)＋大隊 9 藍衣'),
    ('STAIR', 'B1→B2 樓梯上(頭在樓梯下)', [7, 8, 9], '大隊 2 白衣'),
    ('P6', 'B1・樓梯北側(139 前)', [13, 14, 15], '大隊 3 白衣'),
    ('P7', 'B1・140 前', [19, 20, 21, 25, 26, 27], '大隊 4 白衣(靠看台側)＋大隊 5 白衣'),
    ('P8', 'B1・141 前', [31, 32, 33, 37, 38, 39], '大隊 6 白衣(靠看台側)＋大隊 7 白衣'),
    ('P9', 'B1・142–143 前', [43, 44, 45, 49, 50, 51], '大隊 8 白衣(靠看台側)＋大隊 9 白衣'),
]
def fmt_t(v): return '%d:%02d' % (int(v) // 60, int(v) % 60)
out_rows = []
out_rows.append([('藍衣全部 B2 集結版・集結區對照(2026-10-18)', XF_BOLD)])
out_rows.append([('原版大隊 6–9 在 B1 集結、受樓梯三路限制只能三路進場;本版藍衣全部下 B2、白衣 2–9 留 B1,每個大隊都在 6口 會合成六路進場。'
                  '時間為動畫模擬(示意),供比較順序用。', XF_NOTE)])
out_rows.append([])
hdr = ['集結區', '樓層/位置', '成員', '列', '人數', '站法', '進場']
out_rows.append([(h, XF_BOLD) for h in hdr])
for z, where, lies, who in ZONE_ROWS:
    n = sum(files[l]['n'] for l in lies)
    kind = zones[z]['kind']
    how = '死巷:先到的站最裡面,離開時最靠 6口 的先走(休息區排 1 先走)' if kind == 'LIFO' else '頭朝 6口/樓梯:先到的站最前面(休息區排大的先走)'
    da = sorted({files[l]['dadui'] for l in lies})
    ent = '、'.join('大隊 %d(%s)' % (d, fmt_t(min(persons[pid]['t']['gate'] for l in lies if files[l]['dadui'] == d for pid in files[l]['order']))) for d in da)
    out_rows.append([(zlabel(z), XF_BOLD), (where, XF_NOTE), (who, XF_NOTE), ('、'.join(map(str, lies)), XF_NOTE), (n, None), (how, XF_WRAP), (ent, XF_NOTE)])
out_rows.append([])
out_rows.append([('每一列', XF_BOLD)])
hdr2 = ['列', '大隊', '衣色', '集結區', '人數', '休息區座位(依離座順序)', '鏈', '離座波次', '列內離座', '6口 第幾路(北數)', '模擬離座', '模擬到集結區', '模擬過 6口']
out_rows.append([(h, XF_BOLD) for h in hdr2])
for lie in range(1, 55):
    f = files[lie]
    seat = ';'.join('%s:%s～%s(%d人)' % (b['block'].replace('M', ''), b['from'], b['to'], b['n']) for b in f['blocks'])
    waves = '、'.join(sorted({WAVE[b['exitWave']] for b in f['blocks']}))
    lifo = f['direction'].startswith('離座 頭')
    out_rows.append([(lie, None), (f['dadui'], DADUI_XF[f['dadui']]), (f['costume'], XF_NOTE), (zlabel(f['assembly']), XF_NOTE), (f['n'], None),
                     (seat, XF_NOTE), (f['blocks'][0]['chain'], XF_NOTE), (waves, XF_NOTE), ('頭→尾(排 1 先)' if lifo else '尾→頭(排大先)', XF_NOTE),
                     (f['entryIdx'] + 1, None), (fmt_t(f['tLeave']), XF_NOTE), (fmt_t(f['tAssembly']), XF_NOTE), (fmt_t(f['tGate']), XF_NOTE)])
def esc(s): return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
rx = []
for i, r in enumerate(out_rows, 1):
    cs = []
    for j, cell in enumerate(r, 1):
        v, st = cell; ref = n2col(j) + str(i); sa = ' s="%d"' % st if st is not None else ''
        if isinstance(v, (int, float)): cs.append('<c r="%s"%s><v>%s</v></c>' % (ref, sa, v))
        else: cs.append('<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, sa, esc(v)))
    rx.append('<row r="%d">%s</row>' % (i, ''.join(cs)))
widths = [12, 30, 34, 26, 7, 46, 30, 6, 18, 14, 16, 9, 12, 10]
sheet2 = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="%s" xmlns:r="%s"><sheetViews><sheetView workbookViewId="0"/></sheetViews>'
          '<sheetFormatPr defaultRowHeight="16"/><cols>%s</cols><sheetData>%s</sheetData></worksheet>') % (
    NS, RNS, ''.join('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (k, k, w) for k, w in enumerate(widths, 1)), ''.join(rx))

# ---------- styles 寫回 ----------
all_xfs = xf_list + new_xfs
styles_new = styles_txt[:xfs_block.start()] + '<cellXfs count="%d">' % len(all_xfs) + ''.join(all_xfs) + '</cellXfs>' + styles_txt[xfs_block.end():]
fb = re.search(r'(<fonts count=")(\d+)("[^>]*>)(.*?)(</fonts>)', styles_new, re.S)
styles_new = styles_new[:fb.start()] + fb.group(1) + str(n_fonts + 2) + fb.group(3) + fb.group(4) + fonts_add + fb.group(5) + styles_new[fb.end():]

# ---------- 打包 ----------
d2rels = open(f'{U}/xl/drawings/_rels/drawing2.xml.rels', encoding='utf-8').read()
media = re.findall(r'Target="\.\./media/([^"]+)"', d2rels)
ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
      ''
      '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
      '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
      '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
      '<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
      '<Override PartName="/xl/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
      '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
      '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
      '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>')
rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>')
wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="%s" xmlns:r="%s"><bookViews><workbookView activeTab="0"/></bookViews>'
      '<sheets><sheet name="組數_藍衣B2" sheetId="1" r:id="rId1"/><sheet name="集結區對照" sheetId="2" r:id="rId2"/></sheets><calcPr calcId="125725" fullCalcOnLoad="1"/></workbook>') % (NS, RNS)
wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
          '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
          '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
          '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>'
          '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
s1rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
          '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>')
core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>休息區座位 藍衣B2集結版</dc:title><dcterms:created xsi:type="dcterms:W3CDTF">2026-10-18T00:00:00Z</dcterms:created></cp:coreProperties>')
app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Microsoft Excel</Application></Properties>')
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    z.writestr('[Content_Types].xml', ct); z.writestr('_rels/.rels', rels)
    z.writestr('docProps/core.xml', core); z.writestr('docProps/app.xml', app)
    z.writestr('xl/workbook.xml', wb); z.writestr('xl/_rels/workbook.xml.rels', wbrels)
    z.writestr('xl/styles.xml', styles_new); z.write(f'{U}/xl/theme/theme1.xml', 'xl/theme/theme1.xml')
    z.writestr('xl/worksheets/sheet1.xml', sheet1); z.writestr('xl/worksheets/_rels/sheet1.xml.rels', s1rels)
    z.writestr('xl/worksheets/sheet2.xml', sheet2)
    import io
    from PIL import Image
    z.write(f'{U}/xl/drawings/drawing2.xml', 'xl/drawings/drawing1.xml')
    rels2 = d2rels
    for m in media:   # 黑白箭頭/輪椅圖示轉成 1-bit PNG(外觀相同、檔案小)
        src = Image.open(f'{U}/xl/media/{m}')
        if src.mode == 'RGBA':
            bg = Image.new('RGBA', src.size, 'white'); bg.alpha_composite(src); src = bg
        im = src.convert('L').point(lambda v: 255 if v > 128 else 0).convert('1')
        buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True)
        nm = m.rsplit('.', 1)[0] + '.png'
        rels2 = rels2.replace('../media/' + m, '../media/' + nm)
        z.writestr('xl/media/' + nm, buf.getvalue())
    z.writestr('xl/drawings/_rels/drawing1.xml.rels', rels2)
print(OUT, os.path.getsize(OUT))
