# 進場動線版本 3（兩路直進）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `design-explorations/taipei-dome/flow/entry-animation-v3/` 建一個與 2c 並存的完整成品：白藍兩路、不集結、出口坐滿就換，一份 `data.json`、七頁、`seats.csv`、可重算的 `build/`。

**Architecture:** 複製 2c 資料夾為底。`build/` 的 `plan.py`（排序、出口、座位）、`routes.py`（只留直達路線）、`build.py`（單一時鐘、避撞、輸出）、`check.py`（版本 3 檢核）改寫；`base.json`、`geo.py`、`collide.py` 原樣。七頁以 2c 頁為底，資料結構盡量相容，只改集結相關與三路→兩路的顯示。

**Tech Stack:** Python 3 + numpy（建置）、pytest + Playwright（Chromium `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`）、純 HTML/JS（無框架）。

**Spec:** `docs/superpowers/specs/2026-10-22-entry-plan-v3-design.md`（以下 §n 指它）；2c 的設計 `docs/superpowers/specs/2026-10-19-entry-plan-2c-design.md` 與程式 `design-explorations/taipei-dome/flow/entry-animation/` 是複製來源。

## Global Constraints

- 不改 `flow/entry-animation/`（2c）任何檔案，唯一例外是 2c `README.md` 末尾加一行（Task 10）。
- 時間常數：V 1.1、HEADWAY 0.4、STAGGER 0.17、T0 6.73、DADUI_GAP 0.8、STAND_MIN 0.6；避撞 SHIFT_STEP 0.05、SHIFT_MAX 0.15。
- 路 A＝白衣，偏移 +0.12；路 B＝藍衣，偏移 −0.12。
- 出口順序：A 139→140→141→142；B 142→143→144→145；出口坐滿才換；142 先保留 A 需要的席數。
- 每人 `assembly == 'FEEDER'`、`t.assembly == t.enter`、沒有 `adv`；`zones == {}`、`stairSlots == {}`。
- 碰撞只能用個人時間線平移 ≤ 0.15 秒解，解不掉就停下回報，不改規則或幾何。
- 頁面：全中文；只讀 `./data.json`；375px 無橫向捲動；標題、導覽列 aria-label 用「版本 3」，不出現「2c」（連回 2c 總覽的連結文字除外）。
- 腳本確定性：同輸入逐位元相同輸出；`plan.json` 不進 git。
- 不在任何推上 repo 的檔案寫模型名稱。

## Review Focus

1. 142 兩路共用：FIFO 依計畫樓梯時刻，藍衣大隊 1–3 在上排、白衣大隊 9 在下排；出口卡要寫出中間的空檔。→ Task 1 `test_142_shared_fifo`、Task 9 `test_exit_142_two_segments`。
2. 換口落在大隊中間：口令卡、我的路、出口卡對「一列分坐兩個出口」的人要顯示正確出口，不能用該列第一人的出口代表全列。→ Task 6 `test_me_split_column_person`、Task 8 `test_captain_split_dadui`。
3. 某列比同路其他列短：交錯時跳過已排完的列，該列排號順序仍是排大的先。→ Task 1 `test_interleave_skips_exhausted_column`。
4. 大隊交界兩路人數差到 12 人：交界空檔要被檢核接受、且等於規則值。→ Task 3 `test_boundary_gap_matches_rule`。
5. 375px 下總覽的樓梯序 9 格（每格兩行出口，換口的大隊寫兩個）不截斷。→ Task 4 `test_index_mobile_no_hscroll`。

---

### Task 1: 資料夾骨架與 `plan.py`

**Files:**
- Create: `design-explorations/taipei-dome/flow/entry-animation-v3/`（自 2c 複製：`build/base.json`、`build/geo.py`、`build/collide.py`、`build/.gitignore`、七個 html、`core.js`；暫不複製 `data.json`、`seats.csv`、`tests/`）
- Create: `entry-animation-v3/build/plan.py`（以 2c 為底改寫）
- Create: `entry-animation-v3/build/tests/conftest.py`（2c 原樣，`ROOT` 註解改 v3）
- Test: `entry-animation-v3/build/tests/test_plan_lanes.py`、`test_plan_seats.py`、`test_plan_cli.py`、`test_base.py`（2c 原樣）

**Interfaces:**
- Produces（`plan.py`）：
  - `LANES = 'AB'`、`LANE_COSTUME = {'A': '白', 'B': '藍'}`、`LANE_J = {'A': (0, 1, 2), 'B': (3, 4, 5)}`
  - `EXITS`、`EXIT_RANK`、`EXIT_DEF`、`UNUSED_KINDS`、`STAIR_OF`、`seat_usable`、`usable_seats`、`approach`、`aisle_point`、`entry_point`：2c 原樣
  - `EXIT_ORDER = {'A': ['139', '140', '141', '142'], 'B': ['142', '143', '144', '145']}`
  - `lane_sequence(base, lane) -> list[dict]`：每人 `id, lie, pai, dadui, costume, a, lane, laneIdx, dadIdx（該大隊該路內序號 n）, gateLane, slot（同列排大的先，0 起）`
  - `stair_key(p) -> tuple`：`(p['dadui'], p['dadIdx'], LANES.index(p['lane']))`，即計畫樓梯時刻的順序
  - `assign_exits(base, seqs) -> None`：就地寫 `p['exit']`；不夠時 `SystemExit('路 X 缺 N 席')`
  - `nesting_violations(people) -> (list, list)`：依 `stair_key` 合併兩路，回傳（rank 違反清單、同階梯清單）
  - `assign_seats(base, people) -> None`：每出口依 `stair_key` FIFO 配座，寫 `exitSeq, rest, approach, aisle, entry, field, gateIdx`
  - `build_plan(base) -> dict(lanes, exits, groups, people)`，結構見 §5

- [ ] **Step 1: 複製骨架**

```bash
cd design-explorations/taipei-dome/flow
mkdir -p entry-animation-v3/build/tests
cp entry-animation/{index,console,me,score,handout,captain,exit}.html entry-animation/core.js entry-animation-v3/
cp entry-animation/build/{base.json,geo.py,collide.py,.gitignore} entry-animation-v3/build/
cp entry-animation/build/tests/{conftest.py,test_base.py} entry-animation-v3/build/tests/
```

- [ ] **Step 2: 寫失敗測試 `test_plan_lanes.py`**

```python
import plan

def test_lane_sequence_interleaves_three_columns(base):
    A = plan.lane_sequence(base, 'A')
    assert len(A) == 809 and len(plan.lane_sequence(base, 'B')) == 800
    assert [p['lie'] for p in A[:6]] == [1, 2, 3, 1, 2, 3]
    assert all(p['costume'] == '白' for p in A) and [p['laneIdx'] for p in A] == list(range(809))
    d1 = [p for p in A if p['dadui'] == 1]
    assert len(d1) == 87 and [p['dadIdx'] for p in d1] == list(range(87))

def test_interleave_skips_exhausted_column(base):     # Review Focus 3
    for L in 'AB':
        seq = plan.lane_sequence(base, L)
        for lie in {p['lie'] for p in seq}:
            pais = [p['pai'] for p in seq if p['lie'] == lie]
            assert pais == sorted(pais, reverse=True)
            assert [p['slot'] for p in seq if p['lie'] == lie] == list(range(len(pais)))
        for d in range(1, 10):
            ds = [p for p in seq if p['dadui'] == d]
            for a, b in zip(ds, ds[1:]):          # 相鄰兩人不同列，除非其他兩列都已排完
                if a['lie'] == b['lie']:
                    rest = [p for p in ds[ds.index(b):] if p['lie'] != a['lie']]
                    assert not rest

def test_exit_fill_counts(base):
    P = plan.build_plan(base)
    used = {(e, L): sum(1 for p in P['people'] if p['exit'] == e and p['lane'] == L) for e in plan.EXITS for L in 'AB'}
    assert {k: v for k, v in used.items() if v} == {('139', 'A'): 206, ('140', 'A'): 291, ('141', 'A'): 259, ('142', 'A'): 53,
                                                     ('142', 'B'): 202, ('143', 'B'): 185, ('144', 'B'): 198, ('145', 'B'): 215}

def test_nesting_and_distinct_stairs(base):
    P = plan.build_plan(base)
    bad, same = plan.nesting_violations(P['people'])
    assert bad == [] and same == []

def test_split_columns_reported(base):
    P = plan.build_plan(base)
    split = {lie for lie in range(1, 55) if len({p['exit'] for p in P['people'] if p['lie'] == lie}) > 1}
    assert len(split) == 18
    assert P['lanes']['A']['segments'][0]['exit'] == '139' and len(P['lanes']['A']['segments']) == 4 == len(P['lanes']['B']['segments'])
```

- [ ] **Step 3: 寫失敗測試 `test_plan_seats.py`**：從 2c 同名檔改寫，保留「唯一、合法、區＝出口、由上排往下、由出口側往中央」的斷言，另加：

```python
def test_142_shared_fifo(base):                     # Review Focus 1
    P = plan.build_plan(base)
    q = sorted((p for p in P['people'] if p['exit'] == '142'), key=lambda p: p['exitSeq'])
    assert [p['lane'] for p in q] == ['B'] * 202 + ['A'] * 53
    assert {p['dadui'] for p in q[:202]} <= {1, 2, 3} and {p['dadui'] for p in q[202:]} == {9}
    assert P['exits']['142']['order'] == [p['id'] for p in q]
```

- [ ] **Step 4: `test_plan_cli.py`**：2c 原樣，改斷言輸出含 `1609 人`。

- [ ] **Step 5: 跑測試確認失敗**

Run: `cd design-explorations/taipei-dome/flow/entry-animation-v3/build && python3 -m pytest tests/test_plan_lanes.py tests/test_plan_seats.py tests/test_plan_cli.py -q`
Expected: FAIL（`ModuleNotFoundError: plan` 或屬性不存在）

- [ ] **Step 6: 寫 `plan.py`**：以 2c 的 `plan.py` 為底，刪 `BLOCKS / LANE_COL / ASSIGN / ZONE_OF / LIFO_ZONES / column_of / exit_of / check_nesting`，加上 Interfaces 列的函式。`assign_exits`：先算 A 需要的 142 席 = `809 − (139+140+141 可用席)`（由資料算，不寫死），再依 `laneIdx` 填每路；B 在 142 可用 = 142 可用席 − A 保留。`build_plan` 的 `groups`：18 個，順序 大隊 1 白、大隊 1 藍、…、大隊 9 藍；欄位 `key, costume, dadui, lane, population, columns, exits[{exit, n}]`。`lanes[L].segments[{exit, fromIdx, toIdx, n, from:{dadui,lie,pai}, to:{dadui,lie,pai}}]`。`exits[e]`：2c 欄位（`sec, side, stairLabel, entry, rank, capacity, used, rows, order`）。CLI 印 `plan.json 寫出：1609 人；出口用量 {...}`。

- [ ] **Step 7: 跑測試確認通過**

Run: `python3 -m pytest tests/test_plan_lanes.py tests/test_plan_seats.py tests/test_plan_cli.py tests/test_base.py -q`
Expected: 全 PASS

- [ ] **Step 8: Commit**

```bash
git add design-explorations/taipei-dome/flow/entry-animation-v3
git commit -m "feat(taipei-dome): 版本 3 骨架與排位（兩路交錯、出口坐滿就換）"
```

---

### Task 2: `routes.py` 與 `build.py`（單一時鐘）

**Files:**
- Create: `entry-animation-v3/build/routes.py`（2c 精簡）、`entry-animation-v3/build/build.py`（2c 改寫）
- Test: `entry-animation-v3/build/tests/test_routes.py`、`test_build_timing.py`

**Interfaces:**
- Consumes: Task 1 的 `plan.build_plan`、`plan.LANES`、`plan.EXITS`
- Produces:
  - `routes.Geometry(base)`：`B1, B2, LANE_OFF={'A': 0.12, 'B': -0.12}, ST_LANE, STAIR_PTS, GATE_PTS, GATE_DIR`；`arrival_route(person) -> list[(x, y)]`（2c FEEDER 分支）；`stair_top_index(pts) -> int`；`stair_map() -> dict`；`gate_map() -> dict`。常數 `STAIR_U_B1, B2_U_START, STAIR_RUN, LANDING_X, LANDING_END_X, STAIR_HALF_W, GATE_W, GATE_DOORS, GATE_LABEL, JOIN_AHEAD` 同 2c。
  - `build.prepare(G, people) -> {id: dict(arr, L_arr, d_top, k_top)}`
  - `build.schedule(G, people, R, shift=None) -> (sched, clocks)`：`sched[id] = {leave, assembly, enter, gate}`（assembly == enter == 樓梯口時刻），`clocks = {tStairStart, tGateStart, tDadui: {k: 秒}}`
  - `build.assemble(base, planj, G, R, sched, clocks, checks=None) -> data`（§5 結構）
  - `build.avoid(...)`、`build.write_seats_csv(data, path)`、`build.main(argv)`：同 2c 介面

- [ ] **Step 1: 寫失敗測試 `test_routes.py`**

```python
import plan, routes

def test_direct_route_shape(base):
    G = routes.Geometry(base)
    P = plan.build_plan(base)['people']
    for p in (P[0], P[-1]):
        pts = G.arrival_route(p)
        k = G.stair_top_index(pts)
        assert k is not None and pts[-1] == G.GATE_PTS[p['gateLane']]
        assert abs(G.B1.proj(pts[k])[1] - G.LANE_OFF[p['lane']]) < 1e-6

def test_lane_offsets():
    assert routes.LANE_OFF == {'A': 0.12, 'B': -0.12}
```

- [ ] **Step 2: 寫失敗測試 `test_build_timing.py`**

```python
import build, plan, routes

def _sched(base):
    G = routes.Geometry(base); people = plan.build_plan(base)['people']
    R = build.prepare(G, people)
    return people, build.schedule(G, people, R)

def test_first_leave_is_t0_and_no_wait(base):
    people, (S, clocks) = _sched(base)
    assert abs(min(v['leave'] for v in S.values()) - build.T0) < 1e-6
    assert all(v['assembly'] == v['enter'] < v['gate'] for v in S.values())

def test_stair_beats_and_dadui_alignment(base):
    people, (S, clocks) = _sched(base)
    for L in 'AB':
        for d in range(1, 10):
            ts = [S[p['id']]['enter'] for p in people if p['lane'] == L and p['dadui'] == d]
            assert all(abs(b - a - 0.4) < 1e-6 for a, b in zip(ts, ts[1:]))
    ends = {d: max(S[p['id']]['enter'] for p in people if p['dadui'] == d) for d in range(1, 9)}
    starts = {d: min(S[p['id']]['enter'] for p in people if p['dadui'] == d) for d in range(2, 10)}
    assert all(abs(starts[d + 1] - ends[d] - 1.2) < 1e-6 for d in range(1, 9))

def test_total_length_band(base):
    people, (S, clocks) = _sched(base)
    assert 15 < clocks['tGateStart'] < 22 and 330 < max(v['gate'] for v in S.values()) < 360
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_routes.py tests/test_build_timing.py -q`
Expected: FAIL（`ModuleNotFoundError: routes`）

- [ ] **Step 4: 寫 `routes.py`**：自 2c 複製後刪 ZONES、`first_in_zone`、`slot_*`、`advance_*`、`final_zone`、`depart_route`、`gate_join`、`region(s)`、STAIR_SLOTS、ZONE_NMAX、U_SHIFT；`arrival_route(person)` 只剩 FEEDER 那條（座位→`approach`→`B1.off(u_in, off)`→`lane_run` 到 `STAIR_U_B1 − 0.25`→`_down_stair`→`_b2_to_gate(j)`）。`stair_map`、`gate_map`、`trim_corridors`、`miter`、`lane_run`、`poly_between` 原樣。

- [ ] **Step 5: 寫 `build.py`**：`schedule` 用 2c 的 `aligned_clock(items, 'lane', 'dadIdx', 'dadui', stagger, group_gap=DADUI_GAP)`（群序 dadui、路內序 dadIdx，起點相對 0）；`T_S0 = max(T0 + d_top/V − rel)`；`leave = S − d_top/V`、`gate = S + (L_arr − d_top)/V`。`shift` 加到四個時刻。刪 `add_advances / chain_order / ZONE_LABEL 多餘鍵`。`person_path` 只剩 `timed(arr)` + 場內 post 段。`assemble` 依 §5 產出（`zones={}`、`stairSlots={}`、`nodes` 去 P1–P6、`phases` 三段、`files[].exits`、`groups` 補 `tStairFirst, tStairLast, tGateFirst, tGateLast, tAssembly, tLeave, tEnter`、`exits[].segments` 依 Task 1 `lanes` 段切）。`RULES` 與 `ASSUMPTIONS` 依 §3 改寫（至少：兩路與衣色、交錯、出口順序與坐滿就換、142 共用、一個時鐘不停、場內沿原路徑）。CSV「集結區」欄寫「不集結，直接進場」。`meta.title` 照 §5。

- [ ] **Step 6: 跑測試確認通過**

Run: `python3 -m pytest tests/test_routes.py tests/test_build_timing.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add design-explorations/taipei-dome/flow/entry-animation-v3/build
git commit -m "feat(taipei-dome): 版本 3 路線與單一時鐘排程"
```

---

### Task 3: `check.py`、避撞、產出 `data.json` / `seats.csv`

**Files:**
- Create: `entry-animation-v3/build/check.py`
- Create（產出）: `entry-animation-v3/data.json`、`entry-animation-v3/seats.csv`
- Test: `entry-animation-v3/build/tests/test_check.py`

**Interfaces:**
- Consumes: Task 2 的 `build.main`、資料結構 §5
- Produces: `check.check_all(data) -> dict`，鍵 `collisions, nesting, assignment, routes, continuity, noWait, seats, capacity, ok`；`check.COMPARED`（除 `continuity` 外全部）；`check.BOUNDARY_MAX = 7.0`；`check.main(path) -> int`

- [ ] **Step 1: 寫失敗測試 `test_check.py`**（`built` fixture = conftest 的 `pipeline`）

```python
def test_check_all_green(built):
    _, D = built
    C = check.check_all(D)
    assert C['ok'] and C['collisions']['standing'] == 0 == C['collisions']['walking']
    assert C['nesting'] == dict(violations=0, sameStair=0, examples=[])
    A = C['assignment']
    assert A['upstreamViolations'] == 0 == A['notFullSwitches'] and A['segments'] == {'A': 4, 'B': 4} and A['splitColumns'] == 18
    assert C['routes']['crossings'] == 0 and C['noWait']['violations'] == 0
    assert C['capacity']['142'] == dict(used=255, capacity=255, fieldsOk=True)
    assert D['meta']['checks'] == {k: C[k] for k in D['meta']['checks']}

def test_boundary_gap_matches_rule(built):          # Review Focus 4
    _, D = built
    for L in 'AB':
        ps = sorted((p for p in D['persons'] if p['lane'] == L), key=lambda p: p['laneIdx'])
        for a, b in zip(ps, ps[1:]):
            if a['dadui'] != b['dadui']:
                n = {M: sum(1 for p in D['persons'] if p['lane'] == M and p['dadui'] == a['dadui']) for M in 'AB'}
                rule = 0.4 * (max(n.values()) - n[L]) + 0.4 + 0.8
                assert b['t']['enter'] - a['t']['enter'] <= rule + 0.4 + 1e-6 <= check.BOUNDARY_MAX + 0.4
```

另加竄改偵測（每個斷言 `C['ok'] is False`）：
- `test_check_detects_nesting_swap`：把 A 路 laneIdx 0（139）與 B 路 laneIdx 0（142）的 `exit` 對調 → `nesting.violations > 0`
- `test_check_detects_same_stair`：B 路 laneIdx 0 改成 `'140'` → `nesting.sameStair > 0`
- `test_check_detects_early_switch`：A 路最後一位（142）改成 `'141'` 之前的某一位 `'142'` → `notFullSwitches > 0`（或 `upstreamViolations > 0`）
- `test_check_detects_wait`：任一人 `t.enter += 2` → `noWait.violations == 1`
- `test_check_recomputes_capacity_not_trusting_fields`、`test_check_detects_order_list_tampering`：2c 原樣，數字改 140 = 291/291
- `test_check_cli_exit_code`：2c 原樣

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_check.py -q`
Expected: FAIL（`ModuleNotFoundError: check`）

- [ ] **Step 3: 寫 `check.py`**：自 2c 改寫。`nesting` 依 `(dadui, dadIdx, lane)` 合併兩路——資料裡沒有 `dadIdx`，以 `t.enter` 排序合併即可（兩路錯開 0.17 秒，排序穩定）；只比兩路都已開始的時刻。`assignment.notFullSwitches`：每路換口時，前一出口的兩路合計用量 < 可用席即計一次。`routes.crossings`：每大隊六列頭一位（各列 `gateIdx` 最小）取「B2 u ≥ 0.9 且離走廊 < 0.3 起」到 `t.gate + 3` 的折線，15 對兩兩 `_poly_cross`；另 A、B 頭一位從 `t.leave` 到 `t.enter` 的折線 1 對。`continuity`：樓梯兩路以 `t.enter`、依 `laneIdx`，群 = dadui，`GAP 0.25–0.55`、交界 ≤ `BOUNDARY_MAX`；西一入口六路以 `t.gate`、依 `gateIdx`，`minGap ≥ 0.25`、大隊內 ≤ 1.4、順序單調。`noWait`：`assembly != enter`、有 `adv`、或 `path` 在 `leave` 到 `arrive` 間相鄰兩點時間差 > 0.01 而位置相同 → 違反。`seats`、`capacity` 原樣。`ok` 為全部成立（`splitColumns` 不影響）。`main` 印表、與 `meta.checks` 比對 `COMPARED`、exit code。

- [ ] **Step 4: 跑管線**

Run:
```bash
cd design-explorations/taipei-dome/flow/entry-animation-v3/build
python3 plan.py base.json plan.json
python3 build.py base.json plan.json ../data.json ../seats.csv
python3 check.py ../data.json
```
Expected: build 印「全長 3xx 秒 …；檢核 通過」；check 每列 `[OK]`、末行「通過」、exit 0。避撞若留下 `unresolved`：停下，回報碰撞對與時刻，不改規則。

- [ ] **Step 5: 跑測試確認通過**

Run: `python3 -m pytest tests/test_check.py tests/test_build_timing.py tests/test_routes.py tests/test_plan_*.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add design-explorations/taipei-dome/flow/entry-animation-v3
git commit -m "feat(taipei-dome): 版本 3 檢核與產出資料（碰撞 0、巢狀 0）"
```

---

### Task 4: `core.js` 與總覽 `index.html`

**Files:**
- Modify: `entry-animation-v3/core.js`、`entry-animation-v3/index.html`
- Test: `entry-animation-v3/build/tests/test_pages.py`、`test_rules_text.py`、`test_fonts.py`（2c 改寫）

**Interfaces:**
- Consumes: `data.json`（§5）
- Produces（`core.js`，後續頁面共用）：`Dome.LANE_NAME = {A: 'A 路（白衣・靠看台）', B: 'B 路（藍衣・外側）'}`；`Dome.ZONE_NAME.FEEDER = '不集結，直接進場'`（其餘鍵刪除）；`ds.exitsOfFile(lie) -> string[]`；`nav` 的 aria-label「進場動線版本 3 各頁」。其他 API 不變。

- [ ] **Step 1: 寫失敗測試 `test_pages.py`**（2c 檔改寫）

```python
def test_index_overview(open_page):
    pg, errs, perrs = open_page('index.html', 1280)
    pg.wait_for_selector('[data-checks] .ok', timeout=20000)
    assert not errs and not perrs
    assert pg.locator('[data-lane-table] tbody tr').count() == 2
    assert pg.locator('[data-lane-table] tbody tr').first.locator('td').count() == 6     # 路名 + 4 段 + 合計
    assert pg.locator('[data-stair-order] [data-dadui]').count() == 9
    assert pg.locator('[data-exit-usage] [data-exit]').count() == 7
    assert pg.locator('a[href="../entry-animation/index.html"]').count() == 1
    assert '2c' not in pg.title() and '版本 3' in pg.title()

def test_index_mobile_no_hscroll(open_page):          # Review Focus 5
    pg, errs, perrs = open_page('index.html', 375, 700)
    pg.wait_for_selector('[data-checks] .ok', timeout=20000)
    assert no_hscroll(pg) and not perrs
    assert pg.evaluate("[...document.querySelectorAll('[data-stair-order] *')].filter(e=>e.scrollWidth>e.clientWidth+1).length") == 0
```

保留 2c 的 `test_fetch_failure_banner`、`test_data_param_is_not_injected`、`test_data_param_rejects_absolute_url`。`test_rules_text.py`：`meta.rules` 含「白衣」「藍衣」「坐滿」「142」，不含「集結區」「遞補」「死巷」。`test_fonts.py`：2c 原樣。

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_pages.py tests/test_rules_text.py tests/test_fonts.py -q`
Expected: FAIL（列數 3≠2、`[data-dadui]` 0≠9）

- [ ] **Step 3: 改 `core.js`、`index.html`**：照 §6.1。檢核表依 `check.py` 的鍵逐列（項目名稱與門檻寫中文），`splitColumns` 那列顯示「資訊」不標紅綠。樓梯序條每格 `data-dadui="k"`，兩行（白／藍），換口大隊寫「139→140」。

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_pages.py tests/test_rules_text.py tests/test_fonts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**：`feat(taipei-dome): 版本 3 總覽頁`

---

### Task 5: `console.html` 指揮台

**Files:** Modify `entry-animation-v3/console.html`；Test `build/tests/test_page_console.py`（2c 改寫）

**Interfaces:** Consumes Task 4 的 `core.js`。

- [ ] **Step 1: 寫失敗測試**：2c 測試的斷言保留（無錯誤、375 無橫捲、播放後時間前進），改為：上軌格數 `[data-track="stair"] [data-dadui]` == 9、下軌 `[data-track="gate"] [data-dadui]` == 9；路別切換按鈕只有 A、B 兩個；頁面文字不含「集結區」「白 2」「白 3」。
- [ ] **Step 2: 跑測試確認失敗**：`python3 -m pytest tests/test_page_console.py -q` → FAIL
- [ ] **Step 3: 改 `console.html`**：照 §6.2；需要的 `data-track` 屬性加在既有時間軸元素上。
- [ ] **Step 4: 跑測試確認通過**：同上 → PASS
- [ ] **Step 5: Commit**：`feat(taipei-dome): 版本 3 指揮台`

---

### Task 6: `me.html` 我的路

**Files:** Modify `entry-animation-v3/me.html`；Test `build/tests/test_page_me.py`（2c 改寫）

- [ ] **Step 1: 寫失敗測試**：保留 2c 的輸入列排、375 無橫捲、無錯誤；改為步驟數 5（標題依序「起、出、走、進、到」）；新增：

```python
def test_me_split_column_person(open_page, root):      # Review Focus 2
    import json
    D = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    lie = next(l for l in range(1, 55) if len({p['exit'] for p in D['persons'] if p['lie'] == l}) > 1)
    ps = sorted((p for p in D['persons'] if p['lie'] == lie), key=lambda p: p['exitSeq'])
    a, b = next(p for p in ps if p['exit'] != ps[-1]['exit']), ps[-1]
    for p in (a, b):
        pg, _, perrs = open_page(f"me.html?lie={p['lie']}&pai={p['pai']}", 1280)
        pg.wait_for_selector('[data-step="出"]', timeout=20000)
        assert f"{p['exit']} 出口" in pg.inner_text('[data-step="出"]') and not perrs
```

（若 2c 的 me.html 不吃 `?lie=&pai=`，測試改用頁面既有的輸入方式填值；步驟元素加 `data-step` 屬性。）
- [ ] **Step 2: 跑測試確認失敗** → FAIL
- [ ] **Step 3: 改 `me.html`**：照 §6.3；「走」寫同一路前一位是誰（列、排），可能是別列。
- [ ] **Step 4: 跑測試確認通過** → PASS
- [ ] **Step 5: Commit**：`feat(taipei-dome): 版本 3 我的路（五步）`

---

### Task 7: `score.html` 總譜與 `handout.html` 講義

**Files:** Modify `entry-animation-v3/score.html`、`entry-animation-v3/handout.html`；Test `build/tests/test_page_score.py`、`test_page_handout.py`

- [ ] **Step 1: 寫失敗測試**：總譜 54 列，第 1–3 列是列 1、2、3（大隊 1 白），第 4–6 列是列 4、5、6，第 7 列是列 7；頁面文字不含「集結」。講義六格，`[data-moment]` 六個，第三格時刻 == `fmt(meta.tGateStart)`（以頁面上文字比對資料算出的 mm:ss），文字不含「集結區」「白2」。兩頁 375 無橫捲、無錯誤。
- [ ] **Step 2: 跑測試確認失敗** → FAIL
- [ ] **Step 3: 改兩頁**：照 §6.4、§6.5；講義第四、五格時刻取 `lanes.A.segments[1].from` 那位與 `lanes.B.segments[3].from` 那位的 `t.leave`。
- [ ] **Step 4: 跑測試確認通過** → PASS
- [ ] **Step 5: Commit**：`feat(taipei-dome): 版本 3 總譜與講義`

---

### Task 8: `captain.html` 口令卡

**Files:** Modify `entry-animation-v3/captain.html`；Test `build/tests/test_page_captain.py`

- [ ] **Step 1: 寫失敗測試**：保留 2c 的選大隊、375、無錯誤；口令列 `[data-cmd]` 七個（白衣第一位離座、藍衣第一位離座、白衣最後一位離座、藍衣最後一位離座、第一位過西一入口、最後一位過西一入口、全隊到位），時刻與資料算出相同；新增：

```python
def test_captain_split_dadui(open_page, root):          # Review Focus 2
    import json
    D = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    d = next(g['dadui'] for g in D['groups'] if len(g['exits']) > 1)
    pg, _, perrs = open_page(f'captain.html#d{d}', 1280)   # 用頁面既有的選大隊方式
    g = [g for g in D['groups'] if g['dadui'] == d and len(g['exits']) > 1][0]
    text = pg.inner_text('body')
    assert all(e['exit'] in text for e in g['exits']) and '兩個出口' in text and not perrs
```
- [ ] **Step 2–4**：失敗 → 照 §6.6 改 → 通過
- [ ] **Step 5: Commit**：`feat(taipei-dome): 版本 3 口令卡`

---

### Task 9: `exit.html` 出口帶隊卡

**Files:** Modify `entry-animation-v3/exit.html`；Test `build/tests/test_page_exit.py`

- [ ] **Step 1: 寫失敗測試**：保留 2c 的七出口、375（座位圖可橫捲，其餘不可）、無錯誤；新增：

```python
def test_exit_142_two_segments(open_page):              # Review Focus 1
    pg, _, perrs = open_page('exit.html#142', 1280)     # 用頁面既有的選出口方式
    segs = pg.locator('[data-seg]')
    assert segs.count() == 2
    assert 'B' in segs.nth(0).get_attribute('data-seg') and 'A' in segs.nth(1).get_attribute('data-seg')
    assert '空檔' in pg.inner_text('body') and not perrs
```
- [ ] **Step 2–4**：失敗 → 照 §6.7 改（段落元素加 `data-seg="<路>"`）→ 通過
- [ ] **Step 5: Commit**：`feat(taipei-dome): 版本 3 出口帶隊卡`

---

### Task 10: README、首頁卡、release 測試、全套驗收

**Files:**
- Create: `entry-animation-v3/README.md`、`entry-animation-v3/build/README.md`
- Modify: `design-explorations/taipei-dome/index.html`（加一張卡，§6.8）、`flow/entry-animation/README.md`（末尾一行）
- Test: `entry-animation-v3/build/tests/test_release.py`、`test_review_focus.py`

- [ ] **Step 1: 寫失敗測試 `test_release.py`**

```python
def test_hub_has_v3_card(root):
    h = (root.parents[1] / 'index.html').read_text(encoding='utf-8')
    assert h.count('flow/entry-animation-v3/index.html') == 1 and h.count('flow/entry-animation/index.html') == 1
    assert '進場動線 · 版本 3' in h

def test_2c_untouched_except_readme(root):
    r = subprocess.run(['git', 'diff', '--name-only', '4cd340e', '--', str(root.parent / 'entry-animation')], capture_output=True, text=True, cwd=root)
    assert r.stdout.split() == ['design-explorations/taipei-dome/flow/entry-animation/README.md']
```

另保留 2c 的 `test_no_dangling_links`、`test_tracked_outputs_match_pipeline`（逐位元相同）。`test_review_focus.py`：把本計畫 Review Focus 1–5 中尚未在頁面測試覆蓋的資料層斷言放這裡（142 FIFO、交界規則值），2c 檔不搬。

- [ ] **Step 2: 跑測試確認失敗** → FAIL
- [ ] **Step 3: 寫兩份 README、首頁卡、2c README 一行**：README 結構照 2c（是什麼、規則一句話版、出口表、怎麼看、怎麼重算、聲明），內容照版本 3；首頁卡照 §6.8。
- [ ] **Step 4: 全套驗收**

Run:
```bash
cd design-explorations/taipei-dome/flow/entry-animation-v3/build && python3 -m pytest tests -q
cd ../../entry-animation/build && python3 -m pytest tests -q
```
Expected: 兩套全 PASS（2c 的證明沒被改壞）。

- [ ] **Step 5: Commit 並 push**

```bash
git add -A design-explorations/taipei-dome docs/superpowers
git commit -m "feat(taipei-dome): 版本 3 README、首頁卡與發行測試"
git push -u origin claude/admiring-fermi-uraerl
```
