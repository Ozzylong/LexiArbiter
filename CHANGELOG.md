# 更新紀錄

## 如何從 v1.0 升級到 v1.1

1. **把 v1.1 解壓到新的資料夾**，不要直接覆蓋你正在改的資料夾。
2. 依你改過哪些檔案決定怎麼做：

| 檔案 | v1.1 有沒有變 | 你沒改過 | 你改過 |
|---|---|---|---|
| `lexiarbiter/app.py` | **有** | 直接用 v1.1 的 | 以你的版本為主，照下面「一～二」逐項套用 |
| `lexiarbiter/widgets/editor.py` | **有** | 直接用 v1.1 的 | 以你的版本為主，照下面「一、三」逐項套用 |
| `lexiarbiter/core/config.py` | 只多一行註解 | 不用處理 | 不用處理 |
| `core/models.py`、`core/io.py`、`widgets/concept_panel.py`、`widgets/file_panel.py`、`configs/` | 沒變 | 不用處理 | 不用處理 |
| `guide.md`、`CHANGELOG.md`、`tests/`、`.gitignore` | 新增 | 複製過去 | 複製過去 |

> 比對兩個版本最快的方法：在 VS Code 檔案總管對 v1.0 的檔案按右鍵「選取以進行比較」，再對 v1.1 的同名檔案按右鍵「與已選取項目比較」，就會並排顯示每一處差異。

`models.py` 的 TODO 和 `io.py` 的已知問題（見 `guide.md` 附錄）在 v1.1 **沒有**修，仍然是你要完成的部分。

---

## v1.1

### 一、行為變更

#### 1. Popup 選單和工具列標籤按鈕改為二擇一

**位置：** `app.py` → `MainWindow.__init__`、`MainWindow._populate_label_buttons`、`MainWindow._show_quick_label_popup`

- v1.0：popup 和工具列的標籤按鈕同時存在；`auto_popup_on_selection` 只控制 popup 會不會跳。
- v1.1：`configs/user_preferences.json` 的 `auto_popup_on_selection` 在啟動時讀一次：
  - `true` → 選取文字後跳 popup，**工具列不顯示標籤按鈕**
  - `false` → 不跳 popup，改用工具列的標籤按鈕
  - 改設定後要重新啟動程式。

`__init__` 改成：

```python
self.prefs: UserPreferences = UserPreferences.load()
self.use_popup: bool = self.prefs.behavior.get("auto_popup_on_selection", True)   # 新增
...
if self.use_popup:                                                                 # 新增
    self.editor.selection_finished.connect(self._show_quick_label_popup)
```

`_populate_label_buttons` 在移除舊按鈕之後、建立按鈕之前加上：

```python
if self.use_popup:
    return
```

同一個函式裡，每個群組前面原本的 `QLabel(f"  {g.name}：")` 拿掉了，改成只加分隔線；`_build_toolbar` 裡呼叫 `_populate_label_buttons()` 前的那個 `tb.addSeparator()` 也拿掉了。

`_show_quick_label_popup` 開頭這兩行刪除（已經改由 `__init__` 決定要不要接上）：

```python
if not self.prefs.behavior.get("auto_popup_on_selection", True):
    return
```

**如果你已經改過這裡：**
- 你在 `_show_quick_label_popup` 裡加的程式碼照樣保留，只刪上面那兩行（不刪也不會出錯，只是多餘）。
- 你自己把 `selection_finished` 接到別的函式的話，注意 v1.1 在工具列模式下**不會**再接 `_show_quick_label_popup`。工具列模式也要在放開滑鼠時收到通知，見 `guide.md` 1-2「想改行為」。
- 驗收時兩種模式都要能完成標註，兩種都要測。

#### 2. 右鍵選單改版

**位置：** `app.py` → `MainWindow._build_context_menu`

- 沒有反白、右鍵處也沒有標註時：只顯示灰色提示「請先反白文字再標註」，然後 `return`。
- 標籤直接列在選單裡，**不再有群組子選單**；標註資訊那一列只顯示標籤名稱（不含群組名稱）。
- 沒有反白時，略過右鍵處標註已經套用的標籤（再套一次也不會有變化）。
- 「清除『群組』」項目移除（見「二、移除」）。
- 「刪除此處標註」不再有變灰的判斷（無效的情況在函式開頭就 `return` 了）。
- 函式中段新增變數 `ann = self.doc.find_annotation(ann_id) if ann_id is not None else None`，之後可以直接用 `ann`。

**如果你已經改過這裡：** 這個函式改動最多。建議從 v1.1 的 `app.py` 複製整個 `_build_context_menu`，再把你自己加的項目搬進去（`guide.md` 2-1 有說明要加在哪裡）。

#### 3. 右鍵時文字游標移到點擊處

**位置：** `editor.py` → `AnnotationEditor._on_context_menu`

v1.0 沒有反白時，右鍵選單的「專業術語」「刪除此處標註」會作用在**原本文字游標所在的地方**，不一定是你右鍵點到的標註。v1.1 在 `if self._omap is None: return` 之後加了：

```python
# 沒有反白時把文字游標移到右鍵位置，讓「改標籤／刪除此處標註」作用在右鍵處；
# 有反白時不動，避免清掉使用者的選取。
if not self.textCursor().hasSelection():
    self.setTextCursor(cursor)
```

#### 4. 隱藏只有一個群組／一個模式時用不到的介面

**位置：** `app.py`

| 函式 | 改動 |
|---|---|
| `_populate_annotate_menu` | 「標註」選單不再有群組子選單，標籤直接加進 `self.menu_annotate`；子選單裡的「清除『群組』於選取段」移除 |
| `_build_status_bar` | 最後加 `self.status_mode_label.setVisible(False)`，狀態列不顯示模式名稱 |
| `_build_menu` | 「模式」選單最後加 `m_mode.menuAction().setVisible(False)`，整個選單隱藏（切換模式的程式碼仍保留） |

### 二、移除

**位置：** `app.py`

- `MainWindow.clear_group_in_selection`
- `MainWindow._make_clear_group_handler`
- 選單列與右鍵選單裡的「清除『群組』」項目

**如果你的程式有呼叫它們：** 改用 `action_remove_annotation_at_cursor()`（刪除標註），或直接拿掉那個呼叫。

### 三、修正：滑鼠停在標註上沒有 tooltip

**位置：** `editor.py` → `AnnotationEditor`

v1.0 在 `_apply_format_for_labels` 裡用 `fmt.setToolTip(...)` 設定提示，但標註高亮是用 `ExtraSelection` 畫的，這個屬性不會生效，所以停在標註上**從來不會**顯示提示。v1.1 改成自己處理 tooltip：

- `_apply_format_for_labels`：刪掉 `tooltip_parts` 相關的三處（宣告、`append`、最後的 `fmt.setToolTip`）。
- 新增 `# ---- tooltip` 一整段：`_tooltip_text`、`_display_pos_under_mouse`、`_annotations_under_mouse`、`_tooltip_for`、`viewportEvent`、`mouseMoveEvent`。
- `__init__` 新增屬性 `self._tooltip_ann_ids: tuple[str, ...] = ()`。
- import 多了 `QEvent`（`PySide6.QtCore`）、`QToolTip`（`PySide6.QtWidgets`）。

**如果你已經改過 `editor.py`：**
- 從 v1.1 的 `editor.py` 複製整段 `# ---- tooltip`（從 `_tooltip_text` 到 `mouseMoveEvent` 結束），貼在 `_apply_format_for_labels` 後面，再補上 `__init__` 的屬性和 import。
- 你自己也覆寫了 `mouseMoveEvent` 或 `viewportEvent` 的話，兩邊的內容要合併成一個函式，不能留兩個同名函式（後面那個會蓋掉前面的）。
- 想讓 tooltip 多顯示概念名稱，改 `_tooltip_text` 即可（見 `guide.md` 1-9）。

### 四、新增

- `guide.md`：實作指南，包含 GUI 程式的基本邏輯、每個操作對應的函式、怎麼加介面元件，以及驗收清單。
- `tests/`：自我檢查工具，交作業前請先跑過（在專案根目錄執行）：

  ```bash
  python tests/check_code.py                         # 檢查 models.py 的 TODO 與 io.py 的匯出
  python tests/check_lexa.py 你的檔案.lexa            # 檢查存出來的 .lexa 格式
  python tests/check_lexa.py 你的檔案.lexa --task tests/tasks/範例任務.json   # 再和任務單比對
  ```

  - 結果分成 `PASS`、`WARN`（例如範圍只多選或少選了頭尾的空白、標點）、`FAIL`。
  - 和任務單比對時，用文字內容和概念**名稱**比對，`id`、`concept_id` 這些亂數欄位和答案不同沒有關係。
  - `tests/make_answer.py` 是出題用的：依任務單產生答案 `.lexa`，你不需要執行它。
- `.gitignore`
