# SSAdjuster

SSAdjuster 是一個用來矯正 LLM 產生的橫向單列 sprite sheet 的 Python 工具。

它會利用每個 frame 裡的兩種純色標記，自動統一角色的位置與比例：

- 下方 marker：4-12 px 純色、彼此相連色塊。它的中心代表角色中心線，位置代表角色底部錨點。
- 右側尺標 marker：3-5 px 寬的純色垂直線。它的高度代表這個 frame 的角色比例尺，不是角色姿勢的可見高度。

工具預設使用 `auto` 模式：它會直接在整張輸入圖上偵測所有 marker，不要求輸入圖片剛好符合 `frame_width * frame_count`。每個 frame 會依照自己的尺標高度縮放，再把下方 marker 對齊到輸出 frame 的固定位置，移除 marker 顏色，最後重新拼成一張完整的橫向 sprite sheet。

`frame_width` 和 `frame_height` 在 `auto` 模式下代表「輸出 frame 大小」，不是輸入圖片的切格大小。

## 安裝

```bash
pip install -r requirements.txt
```

## 設定

複製 `config.example.json` 成 `config.json`，再依照你的素材修改數值：

```json
{
  "input_path": "input.png",
  "output_path": "output.png",
  "input_mode": "auto",
  "frame_width": 128,
  "frame_height": 128,
  "target_character_height": 90,
  "bottom_padding": 8,
  "ruler_side": "right",
  "bottom_marker_color": "#ff00ff",
  "ruler_marker_color": "#00ff00",
  "debug_output": "output.debug.png"
}
```

主要設定：

- `input_path`：輸入圖片路徑或輸入資料夾。若是資料夾，命令列的 input 會從這個資料夾底下尋找，例如 `input_path` 是 `C:/Users/louis.chu/Pictures/input` 時，執行 `python ss_adjuster.py takeoff.png` 會讀取 `C:/Users/louis.chu/Pictures/input/takeoff.png`。
- `output_path`：輸出圖片路徑或輸出資料夾。若同時指定 `--output`，會在 `output_path` 指定的位置用 `--output` 的檔名輸出；若是資料夾且未指定 `--output`，會沿用 input 的檔名。
- `input_mode`：輸入處理模式。建議使用 `"auto"`；若輸入已經是嚴格固定格，可以用 `"grid"`。
- `frame_width`：輸出時每個 frame 的寬度。
- `frame_height`：輸出時每個 frame 的高度。
- `target_character_height`：目標角色標準高度，也就是 ruler marker 最後要對齊的高度。
- `bottom_padding`：輸出時，角色底部錨點距離 frame 底邊的像素數。
- `ruler_side`：ruler marker 相對於 bottom marker 的方向，可用 `"right"`、`"left"` 或 `"nearest"`。
- `bottom_marker_color`：下方 marker 的顏色。
- `ruler_marker_color`：尺標 marker 的顏色。
- `debug_output`：輸出 debug 圖，方便檢查 marker 偵測位置。

例如 frame 高度是 `128`，`bottom_padding` 是 `8`，那下方 marker 會被對齊到：

```text
y = 128 - 8 = 120
```

也就是角色底部錨點會在 frame 底邊往上 8 px 的位置。

## 執行

預設會讀取目前目錄的 `config.json`。如果裡面已經填好 `input_path` 和 `output_path`，可以直接執行：

```bash
python ss_adjuster.py
```

若 `output_path` 是資料夾，輸出檔會使用 input 的同檔名放到該資料夾。若同時有 `output_path` 和 `--output`，會在 `output_path` 指定的位置使用 `--output` 的檔名。若 `--output` 和 `output_path` 都沒填，會輸出成 `input.output.png` 這類檔名，避免直接覆蓋原圖。

```bash
python ss_adjuster.py input.png --output output.png
```

也可以直接用命令列參數覆蓋設定：

```bash
python ss_adjuster.py input.png --output output.png --input-mode auto --frame-width 128 --frame-height 128 --target-character-height 90
```

如果你的輸入本來就是嚴格固定格，且圖片高度等於 `frame_height`、圖片寬度可被 `frame_width` 整除，也可以使用：

```bash
python ss_adjuster.py input.png --output output.png --input-mode grid --frame-width 128 --frame-height 128 --target-character-height 90
```

## Marker 規則

- 請使用角色圖上不會出現的純色，例如 `#ff00ff` 和 `#00ff00`。
- 每個 frame 都需要一個下方 marker 和一個 ruler marker。
- 下方 marker 的中心代表角色中心線。
- 下方 marker 的位置代表角色底部錨點。
- ruler marker 的高度代表角色比例尺，不是目前姿勢的可見高度。
- 蹲下、彎腰、伸展等姿勢，ruler 仍應代表同一個角色比例，除非你真的想讓該 frame 被額外縮放。
- 請使用 PNG。不要使用 JPG，因為壓縮可能會改變 marker 顏色。
- 輸入 sprite sheet 建議是橫向排列的一列。`auto` 模式不要求輸入寬高剛好符合 frame grid。
- `auto` 模式會按照 bottom marker 的 x 座標排序輸出 frame。
- `auto` 模式下，ruler marker 需要能跟 bottom marker 清楚配對。預設假設 ruler 在 bottom marker 右側。

## 縮放與對齊邏輯

每個 frame 的縮放比例會用以下方式計算：

```text
scale = target_character_height / detected_ruler_height
```

縮放後，工具會把下方 marker 對齊到輸出 frame 的固定位置：

```text
x = frame_width / 2
y = frame_height - bottom_padding
```

最後所有修正後的 frame 會依序橫向拼回：

```text
output_width = frame_count * frame_width
output_height = frame_height
```

在 `auto` 模式下，工具會用這個反向關係從原圖抓取來源範圍：

```text
source_width = frame_width / scale
source_height = frame_height / scale
```

也就是每個 frame 不需要先被切成固定大小；只要 marker 和尺標可被偵測，工具就能推回應該從原圖取哪一塊。

## 其他設定

- `input_mode`：`"auto"` 會全圖偵測 marker；`"grid"` 會用固定 frame 大小切輸入圖。
- `ruler_side`：`"right"` 代表尺標在 bottom marker 右側；如果你的標記習慣不同，可以改成 `"left"` 或 `"nearest"`。
- `marker_tolerance`：偵測 marker 時允許的 RGB 誤差。乾淨 PNG 建議維持 `0`。
- `min_marker_pixels`：marker 至少需要多少像素才會被視為有效。
- `max_bottom_marker_size`：下方 marker 允許的最大寬高。
- `clear_markers`：輸出前是否移除 marker 顏色。
- `output_background_color`：輸出背景色。設為 `null` 代表透明背景，也可以設成 `"#ffffff"` 之類的顏色。
- `debug_output`：輸出一張 debug sheet，會畫出偵測到的 marker 外框與目標中心線/底線。
