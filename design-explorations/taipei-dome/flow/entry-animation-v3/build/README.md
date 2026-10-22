# 版本 3 建置管線

三支腳本串起來，全部確定性，可重現：

```bash
cd build
python3 plan.py  base.json plan.json                           # §3.1–3.3：兩路交錯、出口坐滿就換、出口 FIFO 配座（秒級）
python3 build.py base.json plan.json ../data.json ../seats.csv  # §3.4–3.6：路線、一個時鐘的拉式排程、碰撞避讓、meta.checks（約 40 秒）
python3 check.py ../data.json                                   # §4：檢核全部從 persons / restSeats 重算並與 meta.checks 比對；未通過 exit 1
```

`§` 指設計文件 `docs/superpowers/specs/2026-10-22-entry-plan-v3-design.md`。`plan.json` 是中間檔，不進 git。`build.py --no-avoid` 跳過避撞與檢核。

## 檔案

| 檔 | 內容 |
|---|---|
| `base.json` | 與 2c 相同：版本 1 動畫頁內嵌的 DATA 原樣（場地幾何、座位、場內定位與場內路徑） |
| `plan.py` | 兩路（`LANES`、`LANE_J`）、出口順序（`EXIT_ORDER`）與 `lane_sequence / stair_key / assign_exits / nesting_violations / assign_seats / build_plan`；出口定義、可用席、走道口沿用 2c |
| `routes.py` | 自 2c 精簡：只留「座位 → B1 → 樓梯 → B2 → 西一入口」一條路，兩路偏移 A +0.12、B −0.12 |
| `build.py` | `aligned_clock / schedule / assemble / avoid / write_seats_csv` |
| `check.py` | `check_all(data)` 與 CLI |
| `collide.py`、`geo.py` | 與 2c 相同 |
| `tests/` | pytest：排位、路線、時鐘、檢核（含竄改偵測）、Review Focus、七個頁面（Playwright）、發行（首頁卡、2c 不動、追蹤檔與管線輸出逐位元相同） |

## 依賴

Python 3 與 numpy（建置）；測試另需 `pip install pytest playwright`，Chromium 用預裝的 `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`。跑全部測試：`cd build && python3 -m pytest tests -q`（約 6 分鐘）。

## 檢核與門檻

| 項目 | 門檻 |
|---|---|
| 穿過站定者 / 走路互撞（collide.py 全程） | 0 / 0 |
| 依時間的巢狀：任何時刻白衣出口比藍衣近 / 兩路不在同一座階梯 | 0 / 0 |
| 換口往下游 / 出口還沒坐滿就換 | 0 / 0（分坐兩出口的列只列出） |
| 每大隊六列頭一位的路徑在 B2 不交叉、兩路頭一位在 B1 不交叉 | 0 |
| 不斷拍：樓梯兩路拍距 0.25–0.55 秒、大隊交界 ≤ 7 秒；西一入口六路拍距 ≥ 0.25、≤ 1.4 秒；順序單調 | 成立 |
| 沒有人站著等 | 0 |
| 座位、容量 | 同 2c |

大隊交界放到 7 秒的理由：同一大隊白藍兩路人數最多差 12 人，短的那路在交界空 0.4 × 12 + 0.4 + 0.8 ≈ 6.0 秒，這是兩路人數不等的必然，不是斷拍（設計文件 §4）。
