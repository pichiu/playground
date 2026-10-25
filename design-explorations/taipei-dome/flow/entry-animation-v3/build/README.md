# 版本 3 建置管線

三支腳本串起來，全部確定性，可重現：

```bash
cd build
python3 plan.py  base.json plan.json                           # §3.1–3.3：兩路交錯、出口坐滿就換、出口 FIFO 配座（秒級）
python3 build.py base.json plan.json ../data.json ../seats.csv  # §3.4–3.6：路線、一個時鐘的拉式排程、整排並肩（§3.4c）、碰撞避讓、meta.checks（約 2 分鐘）
python3 check.py ../data.json                                   # §4：檢核全部從 persons / restSeats 重算並與 meta.checks 比對；未通過 exit 1
```

`§` 指設計文件 `docs/superpowers/specs/2026-10-22-entry-plan-v3-design.md`。`plan.json` 是中間檔，不進 git。`build.py --no-avoid` 跳過避撞與檢核。

## 檔案

| 檔 | 內容 |
|---|---|
| `base.json` | 與 2c 相同：版本 1 動畫頁內嵌的 DATA 原樣（場地幾何、座位、場內定位與場內路徑） |
| `plan.py` | 兩路（`LANES`、`LANE_J`）、出口順序（`EXIT_ORDER`）與 `lane_sequence / stair_key / assign_exits / nesting_violations / assign_seats / build_plan`；出口定義、可用席、走道口沿用 2c |
| `routes.py` | 自 2c 精簡：只留「座位 → B1 → 樓梯 → B2 → 門前隊伍隊頭」一條路，兩路偏移 A +0.12、B −0.12；B2 六條線的折線（門前隊伍用） |
| `march.py` | 整排並肩（wheel turn，§3.4c）：隊頭之後的中心線（直線＋圓弧）、六條平移線、間距漸變、時間剖面（外圈步速、內圈依半徑放慢）、各大隊分出點、分出後的梯次進列路線；`export` 寫進 `data.json` 的 `map.march` 給 check.py 驗 |
| `build.py` | `aligned_clock / rank_numbers / schedule / split_points / tail_limits / person_path / assemble / avoid / write_seats_csv` |
| `check.py` | `check_all(data)` 與 CLI；整排並肩的四項在 `formation / wheel / lane_map / geometry` |
| `collide.py` | 2c 的 `collisions`，加上 `seated_hits`（走動中的人與已到位的人） |
| `geo.py` | 與 2c 相同 |
| `tests/` | pytest：排位、路線、時鐘、檢核（含竄改偵測）、Review Focus、七個頁面（Playwright）、發行（首頁卡、2c 不動、追蹤檔與管線輸出逐位元相同） |

## 依賴

Python 3 與 numpy（建置）；測試另需 `pip install pytest playwright`，Chromium 用預裝的 `/opt/pw-browsers/chromium`（舊環境的 `/opt/pw-browsers/chromium-1194/chrome-linux/chrome` 也認得，`tests/conftest.py` 取存在的那一個）。跑全部測試：`cd build && python3 -m pytest tests -q`（約 8 分鐘）。

## 檢核與門檻

| 項目 | 門檻 |
|---|---|
| 穿過站定者 / 走路互撞 / 穿過已坐好的人（collide.py 全程） | 0 / 0 / 0 |
| 依時間的巢狀：任何時刻白衣出口比藍衣近 / 兩路不在同一座階梯 | 0 / 0 |
| 換口往下游 / 出口還沒坐滿就換 | 0 / 0（分坐兩出口的列只列出） |
| 每大隊六列頭一位的路徑在 B2 不交叉、兩路頭一位在 B1 不交叉 | 0 |
| 不斷拍：樓梯兩路拍距 0.2 ± 0.15 秒、大隊交界 ≤ 7 秒；西一入口六路拍距 ≥ 0.59、大隊內 ≤ 1.2、大隊間 ≤ 12 秒；順序單調 | 成立 |
| 步速與門前隊伍：隊伍裡只在自己那條線慢行（≤ 0.125 單位/秒）或站住、不排到側移完成之前；離開隊頭之後不停、不快過步速（路程 ≤ V·Δt + 0.004，路徑存三位小數）；分出之後步速（往西橫走那一段可放慢到 0.7 倍）；t.gate 與自己穿過全壘打牆的時刻差 ≤ 0.01 | 0 |
| 一排六人：同一排一起離開隊頭（差 ≤ 0.01 秒）、排距 ≥ 0.59、大隊 1 全員進隊伍後才出發、同一條線前後相距 ≥ 0.9 格 | 0 |
| 並肩：t.enter → t.split 每 0.1 秒，偏離橫排 ≤ 3°、相鄰兩人距離與設計間距差 ≤ 0.01、排的中心離中心線 ≤ 0.01；每人路徑點離自己那條平移線 ≤ 0.004 | 0 |
| 整排轉彎：由 `map.march` 重算，外圈 ≤ V + 1e-6、內圈半徑 ≥ 0.08、內圈位移沿行進方向單調前進 | 0 |
| lane 對應：lie = 6(大隊 − 1) + gateLane + 1；分出時 lane 0 在最左；進到自己那一列後 \|Y − field.Y\| ≤ 0.005、朝座位單調前進、不越過自己那一列往北 | 0 |
| 幾何避讓：所有路徑每 0.02 細分，只在 `gate.band` 內穿過全壘打牆（每人正好一次）；離舞台線稿（`base.stage` 中 X < −4.5）≥ 0.15 | 0 |
| 座位、容量 | 同 2c |

大隊交界放到 7 秒的理由：同一大隊白藍兩路人數最多差 12 人，短的那路在交界空 0.4 × 12 + 0.4 + 0.8 ≈ 6.0 秒，這是兩路人數不等的必然，不是斷拍（設計文件 §4）。

### 整排轉彎（wheel turn）改了哪些門檻、為什麼（10/25，設計文件 §3.4c）

- **「隊頭到西一入口一排一起 2 秒」→「t.gate = 自己穿過全壘打牆的時刻 ± 0.01」**：舊路線是隊頭到版本 1 收攏點的直線，固定 2 秒。新路線整排沿中心線轉進門，每條線穿牆時刻不同：左轉時內圈 lane 0 先過，相對 t.enter 是 1.40 秒，外圈 lane 5 是 1.56 秒（`meta.turnT` 記最慢那條）。`t.gate` 的語意維持「過西一入口」，me.html 的六步邊界不受影響。
- **同排離開隊頭差、排距的容許 0.16 → 0.01；西一入口拍距下限 0.44 → 0.59**：舊的 avoid 會把個人時間線平移最多 0.15 秒，所以留了 0.16。新做法整排並肩段所有排共用一個速度剖面，不平移時間線，只剩四捨五入，所以收緊。
- **「過門後全程步速」→「離開隊頭之後不快過步速、不停；分出之後步速」**：整排轉彎時內圈依半徑比放慢（第一個左轉內圈最慢 0.3 單位/秒），直線段六人都是步速。進列段的避撞只放慢橫走那一段，最低 0.7 倍。
- **新增「穿過已坐好的人」**：舊碰撞只看門前隊伍站定的人。新路線北行時整排壓過後面大隊的座位、進列時會經過同大隊別人的座位，這一項證明經過時那些座位都還空著。
