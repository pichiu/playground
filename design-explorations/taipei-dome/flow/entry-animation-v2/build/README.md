# v2 頁面資料 · from2c.py

v2 頁面（`../index.html`、`../redesign/`）的外觀與互動不動，`DATA` 由 2c 的 `../../entry-animation/data.json` 轉出，只換 `index.html` 裡 `const DATA = …;` 那一行：

```bash
python3 from2c.py ../../entry-animation/data.json ../index.html
```

2c 重算後要再跑一次；`entry-animation/build/tests/test_release.py` 的 `test_v2_data_follows_2c` 會檢查每個人的時間與路徑都等於 2c。

欄位對照：2c 的「出口 × 路」→ v2 的「區塊 × 鏈」。

- `chain`←lane、`block`←exit、`exitWave`←該路第幾個出口（1–3）、`exitSide`←出口的 N/S
- `walkLane`／`corrLane`←樓梯路 0–2、`laneIdx`←西一入口六路（2c 的 `gateLane`）
- 白 4 以後不集結，在 `nodes` 補一個 `FEEDER`
- `wave01`、`qi`（場內編舞分組）沿用頁面既有值
- `exits`、`lanes`、`groups`、`stairSlots`、`zones` 原樣帶過去，給 `redesign/f-exit.html`

舊的 build／page／excel 腳本（由版本 1 資料重算休息區座位）已移除；git 歷史裡還找得到。
