# 藍衣全部 B2 集結版 · 產生腳本

由版本 1 的 `DATA`(座位、場地幾何、場內路徑)重算。版本 1 頁已移除，`DATA` 原樣存在 2c 的 `base.json`；頁面模板是 `../redesign/src/v1.html`(版本 1 頁原樣):

```bash
# 1. 重排休息區座位、重算路徑與時間
python3 build.py ../../entry-animation/build/base.json new.json plan.json ../休息區座位_藍衣B2集結版.csv
# 2. 碰撞檢查(兩項都必須是 0,否則 exit 1):行進中穿過已站定者(含同一列)、兩個走路的人互撞(全程)
python3 check.py new.json
# 3. 產生頁面(page.py 的每個 rep 都斷言只命中一次，模板改到那些字串時會直接報錯)
python3 page.py ../redesign/src/v1.html new.json ../index.html
# 4. 產生 excel(需 10/17 修正版 xlsx 解壓目錄,當版面底稿)
python3 excel.py <解壓目錄> plan.json new.json 休息區座位_藍衣B2集結版_2026-10-18.xlsx
```

### 資料改用 2c（from2c.py）

v2 頁面（`../index.html`、`../redesign/`）的外觀與互動不動，`DATA` 改由 2c 的 `../../entry-animation/data.json` 轉出：

```bash
python3 from2c.py ../../entry-animation/data.json ../index.html   # 只換 index.html 裡 const DATA = …; 那一行
```

欄位對照：2c 的「出口 × 路」→ v2 的「區塊 × 鏈」（`chain`←lane、`block`←exit、`exitWave`←該路第幾個出口 1–3、`walkLane`／`corrLane`←樓梯路、`laneIdx`←西一入口六路）；白 4 以後不集結，在 `nodes` 補一個 `FEEDER`。`wave01`、`qi` 沿用頁面既有值。2c 重算後要再跑一次，`test_v2_data_follows_2c` 會檢查。下方 build.py／page.py 是舊版 v2 的排法，現在不再用來產生頁面資料。

### 樓梯 L 形與西一入口

`stair.py` 是 2c（`../../entry-animation/build/routes.py`）樓梯／入口圖面的複本（v2 之後會刪，所以不跨資料夾 import；改尺寸時兩邊一起改）：樓梯照企劃圖 6白 的綠色 L 形，直段是樓梯（順著 B1 走廊往南直下），
橫段是樓梯下的 B2 平台（往東接 B2 走廊），三路各自一條斜接折線；6口 改名「西一入口（4 扇門）」，帶寬可 12 人並排。

## 檔案分工

- **git**：產生腳本，以及座位表 `../休息區座位_藍衣B2集結版.csv`（每人的集結區與休息座位，一人一列）。
  改排法時，PR 上可以逐行看出誰換了座位；模擬時間不寫進這個檔。
- **Google Drive**：excel（`休息區座位_藍衣B2集結版_*.xlsx`）由上面第 4 步產生，只放在 Drive 發放，**不進 git**
  （二進位檔看不出差異，而且它的版面底稿 10/17 修正版 xlsx 不在 repo 裡）。
  更新時在 Drive 對既有檔案用「管理版本 → 上傳新版本」，連結不變。

需要 Python 3、numpy、Pillow。build.py 含避撞迭代與收尾全程碰撞自我檢查(與 check.py 同一套判定,見 `collide.py`),約 1 分鐘;check.py 約 30 秒。
