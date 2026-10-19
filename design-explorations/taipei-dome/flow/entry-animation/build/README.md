# 2c 建置管線

三支腳本串起來，全部確定性，可重現：

```bash
cd build
python3 plan.py  base.json plan.json                           # §3.1–3.4：樓梯序、七出口巢狀指派、出口 FIFO 配座（秒級）
python3 build.py base.json plan.json ../data.json ../seats.csv  # §3.5–3.6：路線、兩個連續時鐘的拉式排程、碰撞避讓、meta.checks（約 2 分鐘）
python3 check.py ../data.json                                   # §3.7：六項檢核，重算並與 meta.checks 比對；未通過 exit 1
```

`§` 指設計文件 `docs/superpowers/specs/2026-10-19-entry-plan-2c-design.md`。`plan.json` 是中間檔，不進 git。`build.py --no-avoid` 跳過避撞與檢核（只看幾何與時鐘時用）。

## 檔案

| 檔 | 內容 |
|---|---|
| `base.json` | 版本 1 動畫頁內嵌的 DATA 原樣：場地幾何、座位、場內定位與場內路徑。所有幾何的唯一來源。 |
| `plan.py` | 常數（區塊序、路別對應、出口定義、固定指派表）與 `lane_sequence / check_nesting / usable_seats / approach / assign_seats / build_plan` |
| `routes.py` | 集結區與路線幾何，自版本 2 移植：`Geometry`（ZONES、格位、`arrival_route / depart_route`） |
| `build.py` | `aligned_clock / schedule / assemble / avoid / write_seats_csv` |
| `check.py` | `check_all(data)` 與 CLI |
| `collide.py`、`geo.py` | 版本 2 原檔：碰撞判定（0.01 秒取樣、半徑 0.03）與折線幾何 |
| `tests/` | pytest：規則、座位、幾何、時鐘、檢核、Review Focus、七個頁面（Playwright） |

## 依賴

Python 3 與 numpy（建置）；測試另需 `pip install pytest playwright`，Chromium 用預裝的 `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`（`tests/conftest.py` 的 `CHROME`）。跑全部測試：`cd build && python3 -m pytest tests -q`（約 5 分鐘，含兩次完整管線）。

## 檢核與門檻

| 項目 | 門檻 |
|---|---|
| 穿過站定者 / 走路互撞（collide.py 全程） | 0 / 0 |
| 逐序號巢狀：同一樓梯序號 A 的出口 < B < C | 違反 0 |
| 不斷拍：6口 六路、集結階段樓梯口三路、接尾者樓梯口三路 | 群內拍距 0.25–0.55 秒；群（區塊／大隊）交界對齊空檔 ≤ 5 秒；順序 = 計畫序號 |
| 座位 | 1,609 席唯一、不在 blocked/work、不在 139 的 1–5 號、每出口由上排往下且由出口側往中央 |
| 候隊 | 白3 隊尾 u − 0.1 ≥ 140 接入點 u；白2 全員在樓梯格位 |
| 容量 | 各出口用量 ≤ 可用席 |

## 建置時定下的幾件事（與設計文件初稿不同處）

- 藍衣路別對應是 A = 列 6k−2、B = 6k−1、C = 6k：偏移是走廊折線的固定座標，走進死巷再出來不會左右反序，內側路對內側格位才不交叉。
- 兩個時鐘在群交界各路對齊（6口 另加 0.8 秒大隊空檔）：各欄人數差 1–6 人，不對齊時較短的路會提早帶下一群出來，在集結區頭與場內轉入點穿過還在走的人。
- 版本 1 的 `path[2]` 是當時那條鏈的匯入點，不是走廊邊；2c 取到第一個落在走廊 0.25 內的點為止的折線，末點換成同一 u 的看台側走廊邊 +0.25，再斜向樓梯方向 0.3 併入自己那一路。
- 白3 候隊區 P6：區頭 12.75、間距 0.058，各路就地停在自己那一路。
