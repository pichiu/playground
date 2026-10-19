# 入經藏進場動線 2c 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以「七出口、三路巢狀接尾」規則產生 2c 的 1,609 席座位與全程動線，通過碰撞與巢狀檢核，並把六個看法頁重組成單一成品，取代版本 1／2／2a／2b。

**Architecture:** `build/` 三支 Python 腳本串成管線：`plan.py`（規則 → 樓梯序、出口、座位）→ `build.py`（沿用版本 2 的集結區與路線幾何，改成兩個連續時鐘的拉式排程，寫出 `data.json`／`seats.csv`）→ `check.py`（六項檢核，`build.py` 也引用它寫 `meta.checks`）。前端七頁共用 `core.js`，只讀 `./data.json`。開發期間在 `flow/entry-animation-2c/` 建置，全綠後才刪舊資料夾、改名為 `flow/entry-animation/`、換首頁卡片。

**Tech Stack:** Python 3 + numpy（建置與檢核）、pytest（測試）、Python Playwright 驅動 `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`（頁面測試）、原生 HTML/CSS/JS Canvas（頁面，沿用 redesign 樣式）。

**Spec:** `docs/superpowers/specs/2026-10-19-entry-plan-2c-design.md`

## Global Constraints

- 步速 V = 1.1 單位/秒；HEADWAY = 0.4 秒；LANE_STAGGER = 0.17 秒；同排相鄰離座 ≥ 0.28 秒；T0 = 6.73 秒；站定後 ≥ 0.6 秒才起步；1 單位 ≈ 7.6 m（spec §3.6）。
- 樓梯序：藍9…藍1、白1…白9；路 A/B/C 偏移 +0.12 / 0 / −0.12；白 k 的 A/B/C = 列 6k−5/6k−4/6k−3，藍 k 的 A/B/C = 列 6k−2/6k−1/6k；6口 路 j = (lie−1) mod 6（spec §3.1，建造時修正藍衣對應）。
- 出口巢狀排序 139 < 140 < 141 < 142 < 143 < 144 < 145；指派表固定為 spec §3.3，不搜尋、不拆欄。
- 139 的 1–5 號不用；`kind` 為 blocked/work 的座位不用（spec §3.2）。
- 碰撞處理只允許 spec §3.6 的三階手段；座位與路別不動。
- 檢核門檻依 spec §3.7；群內拍距 0.25–0.55 秒、群交界對齊空檔 ≤ 5 秒、順序 = 計畫序號。
- 全部頁面中文、只讀 `./data.json`、375px 無橫向捲動、無版本切換；時間顯示 mm:ss。
- 開發路徑 `design-explorations/taipei-dome/flow/entry-animation-2c/`；最後一個 task 才改名與刪舊版；在那之前不得刪除或修改 `entry-animation/`、`entry-animation-v2*`。
- 測試一律放 `build/tests/`，用 `Path(__file__)` 定位檔案，不寫死絕對路徑；Playwright 一律 `executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome'`。
- 每個 task 結束 commit；commit message 結尾加上對話中 system-reminder 指定的 `Co-Authored-By` 與 `Claude-Session` 兩行；commit message 不得出現模型識別名稱。

## Review Focus

1. 兩人共用同一走道口（同出口、相鄰排）在 0.4 秒拍距下的 階梯 段：下排的人不得在上排清空前進入階梯。→ Task 7 `test_no_row_overtake`。
2. 白3 候隊尾端與 140 接入點只差 0.1–0.2 單位；白4 A 路第一位進走廊時白3 隊尾必須已經離開。→ Task 7 `test_white3_tail_clear_before_white4`。
3. 白1 C 路在 u≈1.65 換到 P1 格位偏移時，距離藍1 隊尾 0.1 單位；要確認 collide.py 的 0.03 半徑實際通過而不是靠取樣漏掉。→ Task 7 `test_p1_white_blue_clearance`。
4. `me.html` 輸入不存在的位置（如 `55-1`、`1-99`、空白、全形數字）要給可讀的提示而不是例外。→ Task 10 `test_me_invalid_input`。
5. `data.json` 讀取失敗（file:// 開啟、離線）時每頁要顯示提示橫幅而非空白。→ Task 8 `test_fetch_failure_banner`。

---

### Task 1：資料夾骨架與 `base.json`

**Files:**
- Create: `design-explorations/taipei-dome/flow/entry-animation-2c/build/base.json`
- Create: `design-explorations/taipei-dome/flow/entry-animation-2c/build/geo.py`（自 `entry-animation-v2/build/geo.py` 原樣複製）
- Create: `design-explorations/taipei-dome/flow/entry-animation-2c/build/collide.py`（自 `entry-animation-v2/build/collide.py` 原樣複製）
- Create: `design-explorations/taipei-dome/flow/entry-animation-2c/build/.gitignore`（`plan.json`、`__pycache__/`、`.pytest_cache/`）
- Create: `design-explorations/taipei-dome/flow/entry-animation-2c/build/tests/conftest.py`
- Test: `design-explorations/taipei-dome/flow/entry-animation-2c/build/tests/test_base.py`

**Interfaces:**
- Produces: `base.json` = 版本 1 `entry-animation/index.html` 內 `const DATA = …;` 那一行的 JSON 原樣（keys：meta, phases, nodes, map, restSeats, files, persons, others）。
- Produces: `conftest.py` 提供 fixture `root`（= `entry-animation-2c/` 的 Path）與 `base`（載入後的 dict，session scope）。

- [ ] **Step 1: 寫失敗測試 `test_base.py`**

```python
def test_base_shape(base):
    assert set(base) >= {'meta','phases','nodes','map','restSeats','files','persons','others'}
    assert len(base['persons']) == 1609 and len(base['restSeats']) == 1725 and len(base['files']) == 54
    assert base['meta']['speedUnitPerSec'] == 1.1
def test_helpers_copied(root):
    assert (root/'build/geo.py').read_text() == (root.parent/'entry-animation-v2/build/geo.py').read_text()
    assert (root/'build/collide.py').read_text() == (root.parent/'entry-animation-v2/build/collide.py').read_text()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd design-explorations/taipei-dome/flow/entry-animation-2c/build && python3 -m pytest tests/test_base.py -q`
Expected: FAIL（`base.json` 不存在）

- [ ] **Step 3: 抽出 `base.json`，複製 `geo.py`、`collide.py`，建 `.gitignore` 與 `conftest.py`**

抽取指令（與版本 2 README 同法）：`sed -n '/^const DATA = /p' ../../entry-animation/index.html | sed 's/^const DATA = //; s/;$//' > base.json`；寫入前以 `json.load` 驗證可解析。

- [ ] **Step 4: 跑測試確認通過**

Run: 同上
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add design-explorations/taipei-dome/flow/entry-animation-2c docs/superpowers
git commit -m "feat(taipei-dome): 2c 骨架：抽出版本 1 幾何為 base.json，搬入 geo/collide"
```

---

### Task 2：`plan.py` 樓梯序與出口指派

**Files:**
- Create: `…/entry-animation-2c/build/plan.py`
- Test: `…/entry-animation-2c/build/tests/test_plan_lanes.py`

**Interfaces:**
- Produces（模組層常數與函式，後續 task 皆 import `plan`）：
  - `BLOCKS: list[str]` = `['藍9',…,'藍1','白1',…,'白9']`
  - `EXITS: list[str]` = `['139','140','141','142','143','144','145']`；`EXIT_RANK: dict[str,int]`
  - `ASSIGN: dict[str, list[tuple[str,str,str]]]` = spec §3.3（路 → [(出口, 起區塊, 迄區塊)]）
  - `ZONE_OF: dict[str,str]` 區塊 → `'P5'|'P4'|'P3'|'P2'|'P1'|'STAIR'|'P6'|'FEEDER'`
  - `column_of(block: str, lane: str) -> int`（列號）
  - `lane_sequence(base: dict, lane: str) -> list[dict]`：依樓梯序展開的人，每筆 `{id, lie, pai, dadui, costume, block, lane, laneIdx, exit, assembly}`；欄內順序：`ZONE_OF` 為 P2–P5 者 pai 升冪，其餘 pai 降冪
  - `check_nesting(seqs: dict[str, list[dict]]) -> list[dict]`：回傳違反 `EXIT_RANK[A] < EXIT_RANK[B] < EXIT_RANK[C]` 的 `{idx, exits}`，空表為通過

- [ ] **Step 1: 寫失敗測試**

```python
import plan
def test_lane_totals(base):
    seqs = {L: plan.lane_sequence(base, L) for L in 'ABC'}
    assert [len(seqs[L]) for L in 'ABC'] == [535, 537, 537]
    assert [s['block'] for s in seqs['A'][:18]] == ['藍9']*18 and seqs['A'][18]['block'] == '藍8'
def test_block_exits(base):
    seqs = {L: plan.lane_sequence(base, L) for L in 'ABC'}
    by = lambda blk: tuple(sorted({s['exit'] for L in 'ABC' for s in seqs[L] if s['block']==blk}, key=plan.EXIT_RANK.get))
    assert by('藍9') == ('139','141','142') and by('藍4') == ('139','141','144')
    assert by('藍1') == ('140','142','144') and by('白2') == ('140','142','145')
    assert by('白5') == ('140','143','145') and by('白9') == ('141','143','145')
def test_single_exit_per_column(base):
    for L in 'ABC':
        for blk in plan.BLOCKS:
            assert len({s['exit'] for s in plan.lane_sequence(base, L) if s['block']==blk}) == 1
def test_nesting_clean(base):
    assert plan.check_nesting({L: plan.lane_sequence(base, L) for L in 'ABC'}) == []
def test_within_column_order(base):
    A = plan.lane_sequence(base, 'A')
    assert [s['pai'] for s in A if s['block']=='藍9'][:3] == [1,2,3]      # 死巷：排 1 先
    assert [s['pai'] for s in A if s['block']=='白1'][:3] == [28,27,26]   # FIFO：排大先
    assert [s['pai'] for s in A if s['block']=='藍1'][:3] == [33,32,31]   # 藍1 進 P1（FIFO）
def test_exit_usage(base):
    from collections import Counter
    c = Counter(s['exit'] for L in 'ABC' for s in plan.lane_sequence(base, L))
    assert c == {'139':199,'140':283,'141':256,'142':234,'143':179,'144':190,'145':268}
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_plan_lanes.py -q`　Expected: FAIL（`plan` 無法 import）

- [ ] **Step 3: 實作 `plan.py` 的常數與 `column_of`、`lane_sequence`、`check_nesting`**

列人數取 `base['files']` 的 `n`；人員 id 為 `f'{lie}-{pai}'`，`dadui`、`costume`、`a` 由 `base['persons']` 查表。`lane_sequence` 內以 `ASSIGN[lane]` 的區塊區間決定每個區塊的出口（`BLOCKS.index` 比大小）。

- [ ] **Step 4: 跑測試確認通過**　Expected: 6 passed

- [ ] **Step 5: Commit**　`git commit -m "feat(taipei-dome): 2c plan.py 樓梯序與七出口巢狀指派"`

---

### Task 3：`plan.py` 座位、走道口、接入點

**Files:**
- Modify: `…/build/plan.py`
- Test: `…/build/tests/test_plan_seats.py`

**Interfaces:**
- Produces：
  - `EXIT_DEF: dict[str, dict]`：每出口 `{sec, side('N'|'S'), v1block, fill('asc'|'desc'), stairLabel}`；`v1block` = `139,140L,141L,142L,143,144M,145`；`fill`：139、144 為 `desc`，其餘 `asc`
  - `usable_seats(base: dict, exit: str) -> list[dict]`：由上排往下、依 `fill` 排好的可用席 `{sec,pai,no,X,Y}`（扣 blocked/work、139 的 no ≤ 5）
  - `aisle_point(base: dict, exit: str, pai: int) -> tuple[float,float]`：版本 1 中 `block == v1block` 且 `rest.pai == pai` 之任一人的 `path[1][:2]`
  - `entry_point(base: dict, exit: str) -> tuple[float,float]`：該 `v1block` 所有人 `path[2][:2]` 去重後的平均
  - `assign_seats(base: dict, seqs: dict) -> list[dict]`：合併三路、依 `laneIdx` 給每出口 FIFO 序 `exitSeq`（0 起）並配座；每人補 `rest, aisle, entry, exitSeq, gateLane, gateIdx, field, a`
  - `build_plan(base: dict) -> dict`：`{blocks, lanes, exits, people}`，結構見 Task 4
- `gateLane` = `(lie−1) % 6`；`gateIdx` = 同一 6口 路內跨大隊 1→9 的累積序號，欄內 pai 降冪（排大的先過 6口）

- [ ] **Step 1: 寫失敗測試**

```python
import plan
def people(base): return plan.assign_seats(base, {L: plan.lane_sequence(base, L) for L in 'ABC'})
def test_capacity(base):
    assert [len(plan.usable_seats(base, e)) for e in plan.EXITS] == [206,291,259,255,185,198,273]
def test_seats_unique_and_legal(base):
    P = people(base); keys = {(p['rest']['sec'], p['rest']['pai'], p['rest']['no']) for p in P}
    assert len(P) == 1609 == len(keys)
    bad = {(s['sec'],s['pai'],s['no']) for s in base['restSeats'] if s['kind'] in ('blocked','work')}
    assert not (keys & bad) and not any(k[0]=='139' and k[2] <= 5 for k in keys)
def test_exit_fifo_is_top_down(base):
    for e in plan.EXITS:
        q = sorted((p for p in people(base) if p['exit']==e), key=lambda p: p['exitSeq'])
        pais = [p['rest']['pai'] for p in q]; assert pais == sorted(pais, reverse=True)
        for pai in set(pais):
            nos = [p['rest']['no'] for p in q if p['rest']['pai']==pai]
            assert nos == (sorted(nos) if plan.EXIT_DEF[e]['fill']=='asc' else sorted(nos, reverse=True))
def test_exit_seq_follows_lane_idx(base):
    for e in plan.EXITS:
        q = sorted((p for p in people(base) if p['exit']==e), key=lambda p: p['exitSeq'])
        assert [p['laneIdx'] for p in q] == sorted(p['laneIdx'] for p in q)
def test_points(base):
    assert plan.aisle_point(base, '140', 14) and plan.aisle_point(base, '144', 1)
    import math; assert math.dist(plan.entry_point(base,'139'), plan.entry_point(base,'140')) < 0.2
def test_gate_idx(base):
    P = people(base)
    for j in range(6):
        g = sorted(p['gateIdx'] for p in P if p['gateLane']==j); assert g == list(range(len(g)))
    first = min((p for p in P if p['gateLane']==0), key=lambda p: p['gateIdx']); assert (first['lie'], first['pai']) == (1, 28)
```

- [ ] **Step 2: 跑測試確認失敗**　Expected: FAIL（函式不存在）
- [ ] **Step 3: 實作 `EXIT_DEF`、`usable_seats`、`aisle_point`、`entry_point`、`assign_seats`、`build_plan`**
- [ ] **Step 4: 跑測試確認通過**　Expected: 6 passed
- [ ] **Step 5: Commit**　`git commit -m "feat(taipei-dome): 2c plan.py 出口 FIFO 配座與走道口座標"`

---

### Task 4：`plan.json` 輸出與 CLI

**Files:**
- Modify: `…/build/plan.py`（`if __name__ == '__main__'`）
- Test: `…/build/tests/test_plan_cli.py`

**Interfaces:**
- CLI：`python3 plan.py base.json plan.json`；失敗（巢狀、容量、拆欄）以 `SystemExit` 非 0 結束並印出原因。
- `plan.json` 結構：
  - `blocks[]`：`{key, costume, dadui, population, columns[3], assembly, lanes{A|B|C:{lie, exit, n}}}`
  - `lanes{A|B|C}`：`{total, segments[{exit, fromBlock, toBlock, n, fromIdx, toIdx}]}`
  - `exits{key}`：`{sec, side, stairLabel, entry[x,y], rank, capacity, used, rows[{pai, seats[no…], ids[…]}], order[ids]}`
  - `people[]`：Task 3 的欄位全集

- [ ] **Step 1: 寫失敗測試**

```python
import json, subprocess, sys
def test_cli_writes_plan(root, tmp_path):
    out = tmp_path/'plan.json'
    r = subprocess.run([sys.executable, 'plan.py', 'base.json', str(out)], cwd=root/'build', capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    P = json.loads(out.read_text())
    assert set(P) == {'blocks','lanes','exits','people'} and len(P['people']) == 1609 and len(P['blocks']) == 18
    assert [len(P['lanes'][L]['segments']) for L in 'ABC'] == [3,3,3]
    assert P['exits']['139']['used'] == 199 and P['exits']['139']['rows'][0]['pai'] == 12
```

- [ ] **Step 2: 跑測試確認失敗**　- [ ] **Step 3: 實作 CLI 與輸出**　- [ ] **Step 4: 跑測試確認通過**
- [ ] **Step 5: Commit**　`git commit -m "feat(taipei-dome): 2c plan.py 輸出 plan.json"`

---

### Task 5：`routes.py` 集結區與路線幾何（自版本 2 移植）

**Files:**
- Create: `…/build/routes.py`
- Test: `…/build/tests/test_routes.py`

**Interfaces:**
- 以 `entry-animation-v2/build/build.py` 第 26–109 行、226–272 行、462–477 行為底移植，改動只有下列；其餘常數（`ZONES` P1–P5、`U_SHIFT0/1`、`STAIR_U_B1`、`B2_U_START`、`GATE_PTS`、`STAIR_SLOTS`、`slot_offset`、`second_back`、`white_route`）原樣：
  - `class Geometry`：`Geometry(base: dict)`，屬性 `B1, B2, ST`（`geo.Poly`）、`ZONES`、`LANE_OFF = {'A':0.12,'B':0.0,'C':-0.12}`、`STAIR_SLOTS`、`GATE_PTS`
  - `ZONES['P6'] = dict(label='白 3', floor='B1', kind='FIFO', corr='B1', head=12.75, step=-0.058)`；刪除 P7–P9
  - `slot_offset(person)`：P6 回 `LANE_OFF[lane]`；其餘照版本 2 用 `gateLane`（j）計算
  - `first_in_zone(person)`：`dadui == 1 or dadui % 2 == 0 or (dadui == 3 and costume == '白')`
  - `arrival_route(person: dict) -> list[tuple]`：座位 → 走道口 → 接入點 → `B1.off(u_in, LANE_OFF[lane])` → …；B2 走廊與樓梯一律用 `LANE_OFF[lane]`（不用 CHAIN_OFF）；`assembly == 'FEEDER'` 時路線直達 6口：`[seat, aisle, B1.off(u_in, off)] + white_route(j, u_in, off)`
  - `depart_route(person: dict, slot_i: int) -> list[tuple]`：照版本 2；FEEDER 回 `[]`
  - `slot_xy(person, i)`、`slot_u(person, i)`；`regions() -> dict`（版本 2 `region()`，含 P6），並斷言區域互不重疊
  - `stair_top_index(pts) -> int | None`：路線中最接近 `B1.off(STAIR_U_B1, off)` 的點序，供 `build.py` 算通過樓梯口距離
- `person` 為 `plan.json` 的 people 元素（含 `lane, gateLane, assembly, aisle, entry, rest, dadui, costume`）

- [ ] **Step 1: 寫失敗測試**

```python
import json, math, plan, routes
def test_zone_regions_disjoint(base):
    G = routes.Geometry(base); G.regions()   # 內部 assert
    assert 'P7' not in G.ZONES and G.ZONES['P6']['head'] <= 12.75
def test_white3_tail_downstream_of_140(base):
    G = routes.Geometry(base); P = plan.build_plan(base)['people']
    w3 = [p for p in P if p['block']=='白3']
    n_lane = {L: sum(1 for q in w3 if q['lane']==L) for L in 'ABC'}          # 30/29/29
    tail = min(G.slot_u(p, n_lane[p['lane']]-1) for p in w3)
    entry140_u = G.B1.proj(tuple(plan.entry_point(base, '140')))[0]        # ≈ 10.96
    assert tail - 0.1 >= entry140_u
def test_routes_start_and_end(base):
    G = routes.Geometry(base); P = plan.build_plan(base)['people']
    for p in P[::37]:
        pts = G.arrival_route(p); assert pts[0] == (p['rest']['X'], p['rest']['Y'])
        if p['assembly'] == 'FEEDER': assert math.dist(pts[-1], G.GATE_PTS[p['gateLane']]) < 1e-6
        else: assert math.dist(pts[-1], G.slot_xy(p, 0)) < 3.0
def test_stair_slots_fit_white2(base):
    G = routes.Geometry(base); assert all(len(G.STAIR_SLOTS[j]) >= 33 for j in range(3))
```

- [ ] **Step 2: 跑測試確認失敗**　- [ ] **Step 3: 實作 `routes.py`**　- [ ] **Step 4: 跑測試確認通過**
- [ ] **Step 5: Commit**　`git commit -m "feat(taipei-dome): 2c routes.py 移植集結區與路線幾何，白3 候隊改 P6"`

---

### Task 6：`build.py` 兩個時鐘與輸出（尚無避撞）

**Files:**
- Create: `…/build/build.py`
- Test: `…/build/tests/test_build_timing.py`

**Interfaces:**
- CLI：`python3 build.py base.json plan.json ../data.json ../seats.csv [--no-avoid]`
- 模組函式：
  - `phase1_people(people) -> list`：`ZONE_OF[block] != 'FEEDER'`
  - `schedule(G: routes.Geometry, people: list[dict]) -> dict[id, dict]`：每人 `{leave, assembly, enter, gate, arrive, stairPlan, pathArr, pathDep}`，依 spec §3.6：
    - `S(i, lane) = T_S0 + 0.4*i + 0.17*{'A':0,'B':1,'C':2}[lane]`；`T_S0 = T0 + max(d_top/V − 0.4*i − 0.17*k)`（集結階段的人）
    - `G(g, j) = T_G0 + 0.4*g + 0.17*j`；`T_G0 = max(站定者 assembly+0.6+len(dep)/V − 0.4g − 0.17j, 接尾者 T0 + d_gate/V − 0.4g − 0.17j, 集結階段最後站定 + 1.0)`
    - 接尾者 `assembly = enter = leave + d_top/V`
  - `assemble(base, planj, sched) -> dict`：spec §5 的 `data.json`（含 `stairSlots`、`zones`、`exits`、`lanes`、`groups`、`files`、`persons`、`phases`、`meta`）；`meta.checks` 先留空 dict，Task 7 補
  - `write_seats_csv(data, path)`：spec §4.2 欄位
- 6口 之後：取 `base` 同 id 的 `path` 中 `t > t.gate` 的點，自 gate 時刻等速重計時（版本 2 第 509–513 行）。

- [ ] **Step 1: 寫失敗測試**

```python
import json, subprocess, sys, csv
def test_build_no_avoid(root, tmp_path):
    b = root/'build'; subprocess.run([sys.executable,'plan.py','base.json',str(tmp_path/'plan.json')], cwd=b, check=True)
    r = subprocess.run([sys.executable,'build.py','base.json',str(tmp_path/'plan.json'),str(tmp_path/'data.json'),str(tmp_path/'seats.csv'),'--no-avoid'], cwd=b, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    D = json.loads((tmp_path/'data.json').read_text()); P = {p['id']: p for p in D['persons']}
    assert len(P) == 1609 and abs(min(p['t']['leave'] for p in P.values()) - 6.73) < 1e-6
    for p in P.values():
        t = p['t']; assert t['leave'] <= t['assembly'] <= t['enter'] <= t['gate'] <= t['arrive']
        assert p['path'][0][:2] == [p['rest']['X'], p['rest']['Y']] and p['path'][-1][2] == t['arrive']
    for j in range(6):
        g = sorted(p['t']['gate'] for p in P.values() if p['gateLane']==j)
        assert all(abs((b-a)-0.4) < 1e-6 for a,b in zip(g,g[1:]))
    w4 = [p for p in P.values() if p['dadui']>=4 and p['costume']=='白']; assert all(p['t']['assembly']==p['t']['enter'] for p in w4)
    rows = list(csv.DictReader(open(tmp_path/'seats.csv', encoding='utf-8')))
    assert len(rows) == 1609 and list(rows[0]) == ['位置編碼','衣色','大隊','演繹列','演繹位置','休息區','休息排','座號','出口','出口帶隊序','樓梯路','樓梯序號','欄內順序','集結區','6口路','6口序號']
```

- [ ] **Step 2: 跑測試確認失敗**　- [ ] **Step 3: 實作 `build.py`（時鐘、路徑計時、輸出；`--no-avoid` 跳過避撞）**　- [ ] **Step 4: 跑測試確認通過**（本測試約 1 分鐘內）
- [ ] **Step 5: Commit**　`git commit -m "feat(taipei-dome): 2c build.py 樓梯與 6口 兩個連續時鐘的拉式排程"`

---

### Task 7：`check.py` 六項檢核與 `build.py` 避撞

**Files:**
- Create: `…/build/check.py`
- Modify: `…/build/build.py`（避撞迴圈、寫入 `meta.checks`）
- Test: `…/build/tests/test_check.py`、`…/build/tests/test_review_focus.py`

**Interfaces:**
- `check.check_all(data: dict) -> dict`：`{ok: bool, collisions{standing, walking, examples[]}, nesting{violations, indices, examples[]}, continuity{gate{j:{n,minGap,maxGap}}, stairPhase1{lane:{…}}, feederStairTop{lane:{…}}, orderOk}, seats{unique, population, illegal, orderViolations}, staging{white3TailU, entry140U, white2InSlots, ok}, capacity{exit:{used,capacity}}}`；門檻同 spec §3.7（拍距 0.25–0.55）。`data` 需含 `persons[].t.stairPlan`（集結階段者）、`stairSlots`、`zones`、`exits`。
- CLI：`python3 check.py ../data.json`：印表、重算與 `meta.checks` 比對（數字不同也算失敗）、非 ok 則 exit 1。
- `build.py` 避撞：`avoid(G, people, sched, rounds=40)`：每輪跑 `collide.collisions`；對每對碰撞把序號較後者整條時間線 +0.05 秒（同一人累計 ≤ 0.15）；仍有碰撞即記入 `checks.collisions.unresolved` 並讓 `ok=False`。`--no-avoid` 保留。

- [ ] **Step 1: 寫失敗測試**

```python
import json, subprocess, sys, check
def run_pipeline(root, tmp):   # 共用：plan → build（含避撞）
    b = root/'build'; subprocess.run([sys.executable,'plan.py','base.json',str(tmp/'plan.json')], cwd=b, check=True)
    subprocess.run([sys.executable,'build.py','base.json',str(tmp/'plan.json'),str(tmp/'data.json'),str(tmp/'seats.csv')], cwd=b, check=True)
    return json.loads((tmp/'data.json').read_text())
def test_check_all_green(root, tmp_path):
    D = run_pipeline(root, tmp_path); C = check.check_all(D)
    assert C['ok'], json.dumps(C, ensure_ascii=False)[:2000]
    assert C['collisions']['standing'] == 0 == C['collisions']['walking'] and C['nesting']['violations'] == 0
    assert all(0.25 <= v['minGap'] and v['maxGap'] <= 0.55 for v in C['continuity']['gate'].values())
    assert D['meta']['checks']['ok'] is True and D['meta']['checks']['nesting'] == C['nesting']
def test_check_cli_exit_code(root, tmp_path):
    run_pipeline(root, tmp_path)
    r = subprocess.run([sys.executable,'check.py',str(tmp_path/'data.json')], cwd=root/'build', capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
def test_check_detects_tampering(root, tmp_path):
    D = run_pipeline(root, tmp_path); D['persons'][0]['exit'], D['persons'][1]['exit'] = '145', '139'
    assert check.check_all(D)['nesting']['violations'] > 0
```

`test_review_focus.py`（Review Focus 1–3）：

```python
def t_at(p, xy):   # 路徑上最接近 xy 的點的時刻
    return min(p['path'], key=lambda q: (q[0]-xy[0])**2+(q[1]-xy[1])**2)[2]
def test_no_row_overtake(data):   # Review Focus 1
    for e in data['exits']:
        order = [P[i] for i in e['order']]
        for a, b in zip(order, order[1:]):
            if a['rest']['pai'] != b['rest']['pai']:
                assert t_at(b, b['path'][1][:2]) >= t_at(a, a['path'][1][:2]) + 0.28   # 下排第一位到走道口 ≥ 上排最後一位離開走道口 + 0.28
def test_white3_tail_clear_before_white4(data):   # Review Focus 2
    w3A = max((p for p in P.values() if p['dadui']==3 and p['costume']=='白' and p['lane']=='A'), key=lambda p: p['laneIdx'])
    w4A = min((p for p in P.values() if p['dadui']==4 and p['costume']=='白' and p['lane']=='A'), key=lambda p: p['laneIdx'])
    assert t_at(w4A, data['exits_by_key']['140']['entry']) > w3A['t']['enter'] + 0.2   # 白4 A 第一位進走廊時，白3 A 最後一位已起步 0.2 秒以上
def test_p1_white_blue_clearance(data):   # Review Focus 3
    blue1 = [q[:2] for p in P.values() if p['dadui']==1 and p['costume']=='藍' for q in p['path'] if abs(q[2]-p['t']['assembly'])<1e-6]
    for p in (p for p in P.values() if p['dadui']==1 and p['costume']=='白' and p['lane']=='C'):
        for q in p['path']:
            if p['t']['assembly']-3 < q[2] < p['t']['assembly']:
                assert min(math.dist(q[:2], b) for b in blue1) >= 0.05
```
（`data` fixture：session scope，跑一次 pipeline，另掛 `P = {id: person}` 與 `exits_by_key`；`exits[].order` 為位置編碼陣列。）

- [ ] **Step 2: 跑測試確認失敗**　- [ ] **Step 3: 實作 `check.py`、`build.py` 的避撞與 `meta.checks`**　- [ ] **Step 4: 跑測試確認通過**（pipeline 約 2–4 分鐘；若避撞無法收斂，依 spec §3.6 第 3 階停下回報，不繼續後續 task）
- [ ] **Step 5: 產生正式輸出並 Commit**

Run: `python3 plan.py base.json plan.json && python3 build.py base.json plan.json ../data.json ../seats.csv && python3 check.py ../data.json`
Expected: 最後一行 `ok`、exit 0

```bash
git add build/*.py build/tests ../data.json ../seats.csv
git commit -m "feat(taipei-dome): 2c 碰撞避讓與六項檢核，產出 data.json 與 seats.csv"
```

---

### Task 8：`core.js` 與 `index.html` 總覽

**Files:**
- Create: `…/entry-animation-2c/core.js`（以 `entry-animation-v2a/redesign/core.js` 為底）
- Create: `…/entry-animation-2c/index.html`
- Test: `…/build/tests/test_pages.py`（本 task 建立 fixture 與總覽測試）

**Interfaces:**
- `window.Dome`：保留 `load() -> Promise<dataset>`（只讀 `./data.json`）、`pos, state, counts, bounds, fmt(mm:ss，取自 v2 redesign core.js), View, pairs, fail`；移除 `VERSIONS, fetchSets, mode, setMode, switcher, delta`；新增 `nav(current: string)`：把 `<nav class="dome-nav">` 插入 `document.body` 開頭，七項 `總覽 index.html／指揮台 console.html／我的路 me.html／總譜 score.html／講義 handout.html／口令卡 captain.html／出口卡 exit.html`，`current` 加 `aria-current="page"`
- `dataset` 增加：`exits, lanes, groups, blocks(=groups)`, `blockOf(p)`、`exitName(key)`、`nodeName(key)`（`FEEDER` → `不集結，直接接尾下樓`）
- `test_pages.py` fixture：`server`（在 `root` 起 `python3 -m http.server 0`，yield base URL）、`browser`（Playwright chromium，`executable_path` 固定）、helper `open_page(server, browser, path, width) -> (page, console_errors, page_errors)`，`page.goto` 後 `wait_until='load'`

- [ ] **Step 1: 寫失敗測試**

```python
PAGES = ['index.html','console.html','me.html','score.html','handout.html','captain.html','exit.html']
def test_index_overview(server, browser):
    pg, errs, perrs = open_page(server, browser, 'index.html', 1280)
    pg.wait_for_selector('[data-checks] .ok', timeout=15000)
    assert not errs and not perrs
    assert pg.locator('nav.dome-nav a').count() == 7 and pg.locator('a[href="seats.csv"]').count() == 1
    assert pg.locator('[data-lane-table] tbody tr').count() == 3 and pg.locator('[data-stair-order] [data-block]').count() == 18
def test_index_mobile_no_hscroll(server, browser):
    pg, *_ = open_page(server, browser, 'index.html', 375); pg.wait_for_selector('[data-checks]')
    assert pg.evaluate('document.documentElement.scrollWidth') <= 375
def test_fetch_failure_banner(server, browser):   # Review Focus 5
    pg, *_ = open_page(server, browser, 'index.html?data=missing.json', 1280)
    pg.wait_for_selector('#dome-err', timeout=15000)
```
（`?data=` 參數：`Dome.load` 讀 `URLSearchParams` 的 `data`，預設 `data.json`，只為測試失敗路徑。）

- [ ] **Step 2: 跑測試確認失敗**　- [ ] **Step 3: 實作 `core.js` 與 `index.html`**

總覽內容依 spec §6：一句話、六條規則（`meta.rules`）、`data-lane-table`（三路 × 三段，含人數）、`data-stair-order`（18 格依 `groups`，每格三個出口、寬度 ∝ 人數）、七出口用量條、`data-checks` 表（`meta.checks` 全 ok 時容器加 class `ok`，否則逐項紅字＋前三例）、六頁入口卡、下載連結、注意事項。

- [ ] **Step 4: 跑測試確認通過**　- [ ] **Step 5: Commit**　`git commit -m "feat(taipei-dome): 2c core.js 單一資料源與總覽頁"`

---

### Task 9：`console.html` A 指揮台

**Files:**
- Create: `…/entry-animation-2c/console.html`（以 `entry-animation-v2a/redesign/a-console.html` 為底）
- Modify: `…/build/tests/test_pages.py`

**Interfaces:** 使用 Task 8 的 `Dome`。時間軸兩軌：上軌 18 格 `groups`（`tStairFirst`–`tStairLast`，白4 以後用 `tLeave`–`tEnter`），下軌大隊 1–9（`tGateFirst`–`tGateLast`）；三個路別按鈕 `[data-lane="A|B|C"]` 高亮該路正在走的人；集結區標籤旁顯示等候人數。

- [ ] **Step 1: 寫失敗測試**

```python
def test_console(server, browser):
    pg, errs, perrs = open_page(server, browser, 'console.html', 1280)
    pg.wait_for_selector('canvas'); pg.wait_for_function('window.__dome_ready === true', timeout=20000)
    assert not errs and not perrs
    assert pg.locator('[data-track="stair"] [data-block]').count() == 18 and pg.locator('[data-track="gate"] [data-dadui]').count() == 9
    pg.click('[data-lane="B"]'); assert pg.get_attribute('[data-lane="B"]', 'aria-pressed') == 'true'
    pg2, *_ = open_page(server, browser, 'console.html', 375); pg2.wait_for_selector('canvas')
    assert pg2.evaluate('document.documentElement.scrollWidth') <= 375
```
（每頁資料載入並首次繪製後設 `window.__dome_ready = true`。）

- [ ] **Step 2: 跑測試確認失敗**　- [ ] **Step 3: 實作**　- [ ] **Step 4: 通過**　- [ ] **Step 5: Commit**　`git commit -m "feat(taipei-dome): 2c 指揮台頁"`

---

### Task 10：`me.html` B 我的路

**Files:**
- Create: `…/entry-animation-2c/me.html`（以 `entry-animation-v2/redesign/b-journey.html` 為底）
- Modify: `…/build/tests/test_pages.py`

**Interfaces:** 輸入列、排兩格（`#lie`, `#pai`），或 `?id=1-28`。六步卡 `[data-step="起|出|走|集|進|到"]`，文案依 spec §6；找不到時 `#notfound` 顯示「西一＋桃竹只有第 1–54 列，每列最多 34 位」。

- [ ] **Step 1: 寫失敗測試**

```python
def test_me_card(server, browser):
    pg, errs, perrs = open_page(server, browser, 'me.html?id=1-28', 375)
    pg.wait_for_selector('[data-step="到"]'); assert not errs and not perrs
    assert pg.locator('[data-step]').count() == 6 and '140' in pg.inner_text('[data-step="起"]')
    assert pg.evaluate('document.documentElement.scrollWidth') <= 375
def test_me_invalid_input(server, browser):   # Review Focus 4
    for q in ['55-1', '1-99', '１-２８', '-']:
        pg, errs, perrs = open_page(server, browser, f'me.html?id={q}', 375)
        pg.wait_for_selector('#notfound'); assert not perrs
```

- [ ] **Step 2–5**：失敗 → 實作 → 通過 → Commit `git commit -m "feat(taipei-dome): 2c 我的路頁"`

---

### Task 11：`score.html` C 總譜

**Files:** Create `…/score.html`（以 `b`→`c-score.html` 為底）；Modify `test_pages.py`

**Interfaces:** 列順序 = 樓梯序（藍9 三列在最上，白9 最下），每列左側標 `出口·路`；摘要句改為「最長等待在 {區塊}」（`groups` 中 `tGateFirst − tAssembly` 最大者）。

- [ ] 測試：`test_score`：`[data-row]` 共 54、第一個 `data-lie` 為 `54`、`#summary` 內含「最長等待」、375 無橫捲、無錯誤。
- [ ] 失敗 → 實作 → 通過 → Commit `git commit -m "feat(taipei-dome): 2c 總譜頁"`

---

### Task 12：`handout.html` D 講義

**Files:** Create `…/handout.html`（以 `d-keyframes.html` 為底）；Modify `test_pages.py`

**Interfaces:** 六格時刻取自 `phases` 與 `groups`：全員就座（`phases.seated.t1`）、藍9 下樓三路成形（藍9 `tStairFirst`+8）、藍衣 B2 到位＋白1 進 P1（白1 `tAssembly`）、白2 樓梯＋白3 候隊（白3 `tAssembly`）、大隊 1 進場＋白4 接尾（白4 `tLeave`）、全員到位（`meta.tEnd`）。`@page { size: A3 landscape }`。

- [ ] 測試：`test_handout`：`figure[data-key]` 共 6、每格 `canvas` 有繪製（`toDataURL` 長度 > 5000）、無錯誤。
- [ ] 失敗 → 實作 → 通過 → Commit `git commit -m "feat(taipei-dome): 2c 講義頁"`

---

### Task 13：`captain.html` E 口令卡

**Files:** Create `…/captain.html`（以 `entry-animation-v2a/redesign/e-captain.html` 為底）；Modify `test_pages.py`

**Interfaces:** `?k=1..9` 或選單；口令序列（spec §6）：第一位離座、最後一位離座、白衣到齊／藍衣到齊（白4 以後顯示「白衣接尾中」）、6口 交接、出發、最後一位過 6口、全隊到位；六列狀態 `[data-lie]` 六格。

- [ ] 測試：`test_captain`：`captain.html?k=5` → `[data-cue]` ≥ 6、含「白衣接尾中」；`?k=2` 含「白衣到齊」；`[data-lie]` 共 6；375 無橫捲；無錯誤。
- [ ] 失敗 → 實作 → 通過 → Commit `git commit -m "feat(taipei-dome): 2c 口令卡頁"`

---

### Task 14：`exit.html` F 出口帶隊卡與座位圖

**Files:** Create `…/exit.html`（新頁，樣式沿用 e-captain）；Modify `test_pages.py`

**Interfaces:** 左欄 `[data-exit]` 七個（顯示 `used/capacity`）；主區由上排往下 `[data-row]`，每排色帶依大隊、標 `走 A/B/C 路`；段落交界 `[data-handover]` 文案「{區塊} 最後一位 → 換 {出口} 接 {路} 路」；時間列：第一位離座、每段最後一位離座；底部 `canvas#seatmap` 七區並排（席位上大隊色、空席灰），點席位顯示位置編碼於 `#seat-tip`；`@media print` 可印。

- [ ] 測試：`test_exit`：`exit.html?e=141` → `[data-row]` 共 12、第一個含「藍9」、`[data-handover]` ≥ 1（141 由 B 路換到 A 路）、`canvas#seatmap` 存在；`exit.html?e=139` 的 `[data-row]` 最後一個含「空」；375 時 `document.documentElement.scrollWidth <= 375`（座位圖容器自身可橫捲）；無錯誤。
- [ ] 失敗 → 實作 → 通過 → Commit `git commit -m "feat(taipei-dome): 2c 出口帶隊卡與休息區座位圖"`

---

### Task 15：README、取代舊版、首頁卡片、全站連結檢查

**Files:**
- Create: `…/entry-animation-2c/README.md`、`…/entry-animation-2c/build/README.md`
- Delete: `design-explorations/taipei-dome/flow/entry-animation/index.html`、`…/flow/entry-animation-v2/`、`…/flow/entry-animation-v2a/`、`…/flow/entry-animation-v2b/`
- Move: `…/flow/entry-animation-2c/` → `…/flow/entry-animation/`
- Modify: `design-explorations/taipei-dome/index.html`（五張進場卡 → 一張，連到 `flow/entry-animation/index.html`；「模組」一節的進場字樣同步）
- Test: `…/build/tests/test_release.py`

**前置條件：** Task 7 的 `check.py` exit 0 且 Task 8–14 全部測試通過；否則停在這裡回報，不執行刪除與改名。

- [ ] **Step 1: 寫失敗測試**

```python
import re, subprocess
def test_old_versions_gone(root):
    flow = root.parent
    assert root.name == 'entry-animation' and not any((flow/n).exists() for n in ['entry-animation-2c','entry-animation-v2','entry-animation-v2a','entry-animation-v2b'])
def test_hub_single_card(root):
    h = (root.parents[1]/'index.html').read_text(encoding='utf-8')
    assert h.count('flow/entry-animation/index.html') == 1 and 'entry-animation-v2' not in h and '進場動線 · 2c' in h
def test_no_dangling_links(root):   # 掃 taipei-dome 下所有 html 的相對 href/src，檔案都要存在
def test_git_grep_clean(root):
    r = subprocess.run(['git','grep','-n','entry-animation-v2','--','design-explorations'], capture_output=True, text=True, cwd=root)
    assert r.returncode == 1 and r.stdout == ''
```

- [ ] **Step 2: 跑測試確認失敗**
- [ ] **Step 3: 寫兩份 README（spec §7 的指令、依賴、檔案說明、「示意非認證」聲明）；`git rm -r` 四個舊目標；`git mv entry-animation-2c entry-animation`；改首頁卡片**
- [ ] **Step 4: 全部測試重跑一次確認通過**

Run: `cd design-explorations/taipei-dome/flow/entry-animation/build && python3 -m pytest tests -q && python3 check.py ../data.json`
Expected: all passed；`ok`

- [ ] **Step 5: Commit**　`git commit -m "feat(taipei-dome): 進場動線改為單一 2c 成品，移除版本 1/2/2a/2b"`
