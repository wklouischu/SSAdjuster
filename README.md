# SSAdjuster

SSAdjuster 目前以瀏覽器版工具為主。直接開啟 `index.html` 後，可以載入 sprite sheet、檢視裁切框、逐格調整裁切偏移、合併成單列輸出，並用播放預覽確認結果。

## 使用方式

1. 用瀏覽器開啟 `index.html`。
2. 點選「開啟輸入圖」，或把圖片拖曳到 Input 區塊。
3. 設定輸入圖的 `ROW` / `COLUMN`。
4. `Frame W` / `Frame H` 預設可用「平均分配」依 ROW/COLUMN 計算，也可以手動改尺寸。
5. 點選來源圖上的裁切框，或用 Frame 清單選擇要調整的格子。
6. 調整 `Offset X` / `Offset Y`，或使用方向按鈕微調目前 frame 的裁切位置。
7. 設定框線色、背景色 RGBA 與 `Output H`。
8. 在「切割框」與「整併預覽」區使用 `-`、`+`、`1:1`、滑桿或百分比輸入調整預覽倍率，並可在預覽區拖曳平移檢視。
9. 按「播放」檢查輸出動畫；頁面開啟時預設不播放，避免影響設定輸入。
10. 需要比較大小時，開啟另一張序列圖，設定比較圖的 ROW/COLUMN，播放區會依設定同步顯示。
11. 點選「下載 PNG」輸出整併後圖片。

## 裁切模型

- `ROW` / `COLUMN` 會把來源圖切成均分 cell。
- 每個 frame 的裁切框預設置中於自己的 cell。
- `Frame W` / `Frame H` 是裁切框大小。
- `Offset X` / `Offset Y` 是目前選取 frame 相對於該 cell 中心的偏移量。
- 輸出永遠合併為一列，frame 順序為 row-major：從左到右，再由上到下。
- `Output H` 會等比例縮放輸出的 frame 高度；輸出 frame 寬度會依原始 frame 寬高比同步縮放。

## 背景色

背景色使用 `RRGGBBAA` 格式，預設 `00FF00FF`，也就是不透明綠色。

也可以輸入：

- `#RRGGBBAA`
- `RRGGBB`，工具會自動補成 `RRGGBBFF`

整併輸出時會先用背景色填滿，再繪製每個裁切 frame，所以裁切超出來源圖、透明區或空白區都會以背景色填充。

## 比較圖

比較圖會依 Compare 區塊的 ROW/COLUMN 以 row-major 順序播放。載入比較圖時，預設會使用 `ROW = 1`、`COLUMN = 輸出 frame 數`，之後可以手動調整。

若比較圖 frame 數和輸出 frame 數不同，播放時會循環比較圖的 frame。若比較圖寬高無法被 ROW/COLUMN 整除，播放區會顯示提醒。

