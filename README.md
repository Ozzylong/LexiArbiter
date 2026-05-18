# LexiArbiter

針對法律判決進行 multi-task learning 標註資料製作的桌面 GUI 工具。
讀取司法院 open data JSON 檔（取 `JFULL` 欄位），以螢光筆方式標註不同類別的文字片段，
並可匯出 model-ready 的 `.txt` 檔（如 `<P>大前提,非第一人稱|...</P>` 形式）。

## 主要特色

- **多群組標籤**：同一段文字可同時帶有多個群組的標籤（例如「主任務：論證類別」+「輔助任務：人稱」），符合 MTL 訓練資料結構。
- **三種觸發方式**：上方按鈕、可自訂的鍵盤快速鍵、滑鼠右鍵選單，適應不同使用者習慣。
- **接力標註友善**：除了 model-ready `.txt` 之外，可另存為專屬 `.lexa` 進度檔（含完整原文 + 已標註資料），方便另一位標註者開檔接續。
- **可切換的標註模式**：標註欄位、按鈕、顏色、輸出格式由 `configs/annotation_modes/*.json` 描述，使用者可新增模式檔並在「標註模式」選單即時切換。
- **使用者偏好分離**：個人快速鍵習慣存於 `configs/user_preferences.json`，不會誤改到輸出格式。
- **同資料夾檔案瀏覽**：右側面板列出同資料夾的判決檔案，雙擊即可切換、附帶未存檔提示。

## 安裝（從原始碼）

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python main.py
```

需要 Python 3.10 以上版本（建議 3.11）。

## 打包成 Windows .exe

```bash
pip install pyinstaller
python build_exe.py
```

完成後會在 `dist/LexiArbiter/` 產出一份資料夾，內含 `LexiArbiter.exe`、PyInstaller 的 `_internal/` 相依、以及 `configs/`、`assets/`。整個資料夾保留在一起即可分發（壓 zip 給使用者解開就能跑）。
使用者可直接編輯 `configs/` 內的 JSON 來新增/調整標註模式，無需重新打包。

## 檔案類型

| 副檔名 | 用途 | 由誰產生 |
| --- | --- | --- |
| `.json` | 司法院判決 open data 原始檔，會讀取 `JFULL` | 外部資料來源 |
| `.lexa` | LexiArbiter 進行中的標註檔，內容為 JSON，含完整原文 + 已標註資料；用來在多人之間接力 | LexiArbiter「儲存進度」 |
| `.txt` | Model-ready 匯出檔，每行一個 `<P>tag1,tag2|文字</P>` 段落 | LexiArbiter「匯出」 |

## 預設標註模式（`legal_mtl`）

| 群組 | 角色 | 類別 | 預設快速鍵 |
| --- | --- | --- | --- |
| 論證類別 (主任務) | primary | 程序 / 事實 / 大前提 / 小前提 / 心證其他 / 結論 | Ctrl+1 ~ Ctrl+6 |
| 人稱 (輔助任務) | auxiliary | 第一人稱 / 非第一人稱 | Ctrl+Shift+1 / Ctrl+Shift+2 |

## 標註模式設定範例

```json
{
  "id": "my_mode",
  "name": "我的標註模式",
  "groups": [
    {
      "id": "topic",
      "name": "主題",
      "role": "primary",
      "labels": [
        {"id": "a", "name": "甲", "tag": "甲", "color": "#FFD54F", "shortcut": "Ctrl+1"},
        {"id": "b", "name": "乙", "tag": "乙", "color": "#64B5F6", "shortcut": "Ctrl+2"}
      ]
    }
  ],
  "export": {
    "tag_order": ["topic"],
    "tag_separator": ",",
    "wrapper_open": "<P>",
    "wrapper_close": "</P>",
    "field_separator": "|",
    "include_unannotated": false,
    "require_all_groups": false
  }
}
```

把這個檔案放進 `configs/annotation_modes/` 後，於選單「標註模式」即可切換。

## 使用流程

1. **檔案 → 開啟檔案**（或點右側清單）→ 選擇 `.json` 或 `.lexa`。
2. 用滑鼠選取要標註的文字，
   - 點上方對應顏色的按鈕、
   - 或按設定好的快速鍵、
   - 或在文字上點右鍵叫出選單，
3. 同一段可重覆套用其他群組的標籤（例如先「大前提」、再「非第一人稱」）。
4. **檔案 → 儲存標註進度** 存成 `.lexa`（接力工作建議用此格式）。
5. 全部標註完成後 **檔案 → 匯出模型用 .txt** 取得最終訓練資料。

## 鍵盤總覽（預設）

- 開啟 `Ctrl+O` / 儲存 `Ctrl+S` / 匯出 `Ctrl+E`
- 刪除游標處或選取段標註 `Ctrl+D`
- 切換到上一個 / 下一個檔案 `Alt+Up` / `Alt+Down`
- 標籤快速鍵見上面表格，可在 `configs/user_preferences.json` → `shortcut_overrides` 內覆寫
