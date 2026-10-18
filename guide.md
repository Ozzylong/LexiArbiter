# 術語—解釋標註功能 實作指南

這份指南分成三個部分：

- **第零部分：GUI 程式的基本邏輯**：GUI 程式和一般 Python script 跑法不一樣。沒寫過 GUI 的話請先讀這部分，後面的流程圖才看得懂。
- **第一部分：程式運作對照**：你在程式裡做的每個操作（選文字、按按鈕、按右鍵…），各自對應到哪些函式、呼叫了什麼、回傳了什麼。想改某個操作的行為時，要去改哪裡。
- **第二部分：GUI 元件怎麼產生、怎麼加**：如果想在右鍵選單或工具列多加一個按鈕、擴充概念對話框，要去哪個函式、可以照抄 template 裡的哪一段。

> 位置一律用「檔案 → 類別.函式」標示。請用編輯器的搜尋或「跳至定義」功能找到它們。
> `MainWindow` 在 `lexiarbiter/app.py`，`AnnotationEditor` 在 `lexiarbiter/widgets/editor.py`。

---

## 目標：要存進去的資料

功能和介面怎麼設計都由你決定，但**建立出來的標註必須符合以下格式**。

`Annotation`（`lexiarbiter/core/models.py`）

| 欄位 | 要存什麼 | 值通常從哪裡拿 |
|---|---|---|
| `start`, `end` | 術語的範圍 | 使用者選取術語時呼叫 `self.editor.storage_selection()` |
| `labels` | 固定為 `{"entity": "term"}` | `apply_label(group_id, label_id)` 收到的參數 |
| `explanation_start`, `explanation_end` | 解釋段落的範圍 | 使用者選取解釋時呼叫 `self.editor.storage_selection()` |
| `concept_id` | 綁定概念的 id | `self.doc.concepts` 中的某個 key |
| `broader_concept_id` | 上位概念的 id | `self.doc.concepts` 中的某個 key |

`Document.concepts`（同一個檔案）是整份文件共用的概念清單，格式為 `{概念id: 概念名稱}`。
新概念的 id 請沿用現有寫法：`"C_" + uuid.uuid4().hex[:8]`。

做完後，存出來的 `.lexa` 應該長這樣：

```json
{
  "concepts": { "C_1a2b3c4d": "過擬合", "C_9f8e7d6c": "機器學習問題" },
  "annotations": [
    {
      "start": 120, "end": 123,
      "labels": { "entity": "term" },
      "concept_id": "C_1a2b3c4d",
      "explanation_start": 124, "explanation_end": 180,
      "broader_concept_id": "C_9f8e7d6c"
    }
  ]
}
```

存檔和讀檔都已經支援這些欄位，你只要在建立 `Annotation` 時把值填進去即可。

---

# 第零部分：GUI 程式的基本邏輯

## 0-1. 一般程式 vs GUI 程式

你平常寫的 Python script 是**從第一行跑到最後一行，跑完就結束**。

GUI 程式不一樣：它先把畫面「蓋好」，然後進入一個叫 **event loop** 的迴圈，**一直等**，直到你關閉視窗為止。等待的過程中，只要使用者做了某個動作（按按鈕、拖選文字、按右鍵），程式才會去執行對應的函式，執行完又回去繼續等。

可以想像成餐廳的服務生：開店時先把桌椅擺好（蓋畫面），然後就站在旁邊等；客人舉手（事件），服務生才過去處理，處理完再回去等下一位。

這個 template 的時間軸長這樣：

```
main.py 啟動
  → MainWindow.__init__()      蓋畫面：建立按鈕、選單、編輯器，並「登記」每個事件發生時要呼叫哪個函式
  → app.exec()                 進入 event loop，開始等（在 main.py 裡）
       ├─ 使用者按「開啟檔案」  → Qt 自動呼叫 MainWindow.action_open()   → 回去繼續等
       ├─ 使用者拖選文字        → Qt 自動呼叫對應的函式（見 1-2）        → 回去繼續等
       ├─ ……
       └─ 使用者關閉視窗        → 離開 event loop，程式結束
```

所以在 GUI 程式裡，**你寫的函式大多不是由你自己呼叫的**，而是「事先登記好，等事件發生時由 Qt 幫你呼叫」。

---

## 0-2. 三個角色：元件、signal、處理函式

| 角色         | 是什麼             | template 裡的例子                                                                     |
| ---------- | --------------- | --------------------------------------------------------------------------------- |
| 元件（widget） | 畫面上看得到的東西       | 工具列按鈕、編輯器 `self.editor`、右側檔案清單 `self.file_panel`                                  |
| signal（事件） | 元件「發生某件事」時發出的通知 | `triggered`（按下工具列 / 選單項目）、`clicked`（按下 `QPushButton`）、`selection_changed`（選取範圍改變） |
| 處理函式（slot） | 事件發生時要執行的函式     | `MainWindow.action_open`                                                          |

把這三者串起來的就是 `connect`：

```python
元件.signal.connect(處理函式)
```

意思是「**登記**：當這個元件發生這件事時，請呼叫這個函式」。登記的當下，函式**不會**執行。

---

## 0-3. Show case：拆解「開啟檔案」按鈕，再自己做一個

**先看現有的程式碼。** 在 `MainWindow._build_toolbar` 裡，「開啟檔案」按鈕只有兩行：

```python
a_open = tb.addAction(_swatch_icon("#FFFFFF"), "開啟檔案")   # ① 建立元件：在工具列 tb 上加一個按鈕
a_open.triggered.connect(self.action_open)                  # ② 登記：按下（triggered）時呼叫 action_open
```

③ 處理函式 `MainWindow.action_open` 定義在 `MainWindow` 的其他地方。程式啟動時它**不會**跑；之後**每按一次按鈕，Qt 就呼叫它一次**。

```
程式啟動時（只跑一次）：
MainWindow.__init__ → _build_toolbar
   ├─ ① 建立「開啟檔案」按鈕
   └─ ② a_open.triggered.connect(self.action_open)

之後每次使用者按下按鈕：
按鈕 ⇢ emit triggered
     ⇢ 接到 MainWindow.action_open()     ← ③ 跳出選擇檔案的視窗
```

**照樣做一個自己的按鈕。** 以下示範加一個「選取字數」按鈕，按下後在狀態列顯示目前選了幾個字（只用到第一部分會介紹的 `storage_selection()` 和 `status.showMessage()`，可以先照抄）：

```python
# ① ② 加在 MainWindow._build_toolbar 裡，「開啟檔案」那幾行的旁邊
a_count = tb.addAction(_swatch_icon("#FFFFFF"), "選取字數")
a_count.triggered.connect(self.show_selection_length)

# ③ 在 MainWindow 類別裡新增這個函式
def show_selection_length(self):
    if self.doc is None:                                   # 還沒開檔就按，先擋掉
        self.status.showMessage("請先開啟檔案", 3000)
        return
    s, e = self.editor.storage_selection()                 # 取得選取範圍（見 1-2）
    self.status.showMessage(f"目前選取 {e - s} 字", 3000)  # 在狀態列顯示 3 秒
```

> 這只是練習用的範例，template 裡沒有這個按鈕。想加任何 GUI 元件都是同樣三步：**① 建立元件 → ② connect 到函式 → ③ 寫出那個函式**。第二部分的每一節，都只是在告訴你 ① 要寫在哪裡、用什麼元件。

---

## 0-4. 常見錯誤

- **connect 時多加了括號**

  ```python
  a_count.triggered.connect(self.show_selection_length)     # ✓ 把「函式本身」交給 Qt，等按下時再呼叫
  a_count.triggered.connect(self.show_selection_length())   # ✗ 加了括號 = 現在就呼叫，
                                                            #   把回傳值（None）拿去登記，之後按了沒反應或報錯
  ```

- **想在呼叫時多帶參數**：`connect` 只能接「函式本身」，要帶參數就用 `lambda` 包一層，template 裡可以照抄的地方見 2-1。
- **不要假設使用者一定照順序操作**：處理函式可能在任何時候被呼叫（例如還沒開檔就按按鈕），開頭先檢查狀態，像上面範例的 `if self.doc is None:`。

---

## 0-5. 用這個角度看整個 template

事件不一定是「按按鈕」。下面是 `MainWindow.__init__` 裡實際的幾條接線：

| 誰發出                         | signal                      | 接到                            | 說明                          |
| --------------------------- | --------------------------- | ----------------------------- | --------------------------- |
| 工具列「開啟檔案」                   | `triggered`                 | `action_open`                 | 使用者按下按鈕                     |
| `self.editor`               | `selection_changed(s, e)`   | `_on_selection_changed`       | 選取範圍改變，順便把範圍 `s, e` 當參數傳過來  |
| `self.file_panel`           | `file_open_requested(path)` | `_handle_file_open_requested` | 在檔案清單點兩下，把檔案路徑傳過來           |
| `self._autosave_timer`（計時器） | `timeout`                   | `_autosave_tick`              | 每 60 秒自動觸發一次，**不需要使用者做任何事** |

除了 `connect`，還有第二種接事件的方式：**覆寫事件函式**。像 `AnnotationEditor.mouseReleaseEvent` 這種名字固定的函式，Qt 會在「放開滑鼠」時自動呼叫它。template 在這個函式裡判斷完狀況後，再 `emit` 自己定義的 signal（例如 `selection_finished`）通知 `MainWindow`，`MainWindow` 那邊再用 `connect` 接起來（見 1-2；1-8 要你自己接一條）。

**第一部分的每一張流程圖，其實都在回答同一個問題：「哪個事件發生了 → 它被 connect 到哪個函式 → 那個函式做了什麼」。** 想加新功能，就是「挑一個事件 → connect 到你寫的函式」。

---

# 第一部分：程式運作對照

## 怎麼讀這一部分

程式裡的函式可以分成兩種：

- **事件流程**：使用者做了某個動作（放開滑鼠、按按鈕、按右鍵）之後，程式**自動**依序執行的函式。你不需要自己呼叫，只要知道它們會被執行，想改行為時就去改那個函式。
- **查詢函式**：**不會自己執行**，要你在自己的程式裡主動呼叫，用來詢問目前的狀態。例如「使用者選了哪一段？」「游標停在哪個標註上？」。

下面每張流程圖都會把這兩種函式畫在一起：事件流程是主線；主線上的某個函式如果呼叫了查詢函式，就會畫成往下長出的分支，並寫出它回傳什麼。
**你自己寫程式時，就在同樣的位置、用同樣的方式呼叫這些查詢函式。**

圖例：

```
A → B                       A 執行完後，自動接著執行 B
A
  └─ 呼叫 xxx() → 回傳值      A 函式內部主動呼叫了 xxx()，並拿到回傳值
⇢ emit 某signal(參數)         透過 signal 把參數送出去
⇢ 接到 某函式(參數)            這個 signal 在 MainWindow.__init__ 裡被 connect 到某個函式，所以那個函式會被呼叫
```

> 不熟 signal、`emit`、`connect` 的話，請先看第零部分。

---

## 1-1. 開啟檔案

```
選單「檔案 → 開啟檔案」/ 工具列「開啟檔案」 → MainWindow.action_open()
右側檔案清單點兩下                             → MainWindow._handle_file_open_requested(path)
        ↓
MainWindow.load_file(path)
   └─ 呼叫 io.load_any(path) 或 io.parse_legacy_txt(...) → 回傳 Document
   ├─ self.doc = doc                                    ← 從這裡開始，self.doc 就是目前的文件
   ├─ self.editor.attach(doc, self.mode, self.prefs)    ← 把文字放進編輯器並畫出高亮
   └─ self.concept_panel.refresh(doc)                   ← 更新右下角的概念清單
```

- 在 `MainWindow` 裡，**目前的文件是 `self.doc`**（沒開檔時是 `None`），原文字串是 `self.doc.text`，所有標註在 `self.doc.annotations`。
- 想在開檔後多做一件事，就加在 `load_file` 的最後面。

---

## 1-2. 在編輯器裡拖選文字

拖選會觸發**兩條**流程：

**流程 A：放開滑鼠（拖選結束）時跑一次**

```
按下左鍵 → AnnotationEditor.mousePressEvent(ev)       ← 記下「左鍵拖曳開始了」
放開左鍵 → AnnotationEditor.mouseReleaseEvent(ev)
              └─ 呼叫 self.has_selection() → True / False          「有沒有選到字？」
                    └─ （它內部是呼叫 self.storage_selection() → (s, e)，再判斷 e > s）
              有選到字（True）：
              ⇢ emit selection_finished(滑鼠放開位置的螢幕座標)
              ⇢ 接到 MainWindow._show_quick_label_popup(global_pos)     → 見 1-3
                    ※ 這個函式收到的參數只有「螢幕座標」，不包含選取範圍。
                    ※ 想在這裡知道使用者選了什麼，要自己呼叫：
                         s, e = self.editor.storage_selection()
                         text = self.doc.text[s:e]
```

> `selection_finished` 只有在 popup 模式（`auto_popup_on_selection: true`）時，才會在 `MainWindow.__init__` 接到 `_show_quick_label_popup`。工具列模式下，流程 A 走到 emit 就停了，沒有任何函式被呼叫。

**流程 B：選取範圍只要有變動就跑（拖曳過程中會一直跑，鍵盤選取也會跑）**

```
選取範圍改變 → AnnotationEditor._on_selection_changed()
                 └─ 呼叫 self.storage_selection() → (s, e)
                 ⇢ emit selection_changed(s, e)
                 ⇢ 接到 MainWindow._on_selection_changed(s, e)     ← 在狀態列顯示「選取 N 字：…」
                       ※ 範圍已經透過參數 s, e 傳進來了，這裡不需要再呼叫 storage_selection()
                       ※ 函式內用 self.doc.text[s:e] 取出文字
```

### 這幾個「取得選取」的方法差在哪？

| 你在哪裡 / 你需要什麼                                                        | 用什麼                                      | 說明                                                        |
| ------------------------------------------------------------------- | ---------------------------------------- | --------------------------------------------------------- |
| 任何地方，需要**選取範圍**                                                     | `s, e = self.editor.storage_selection()` | 最基本的查詢函式，回傳 `(start, end)`；沒選取時 `s == e`                  |
| 任何地方，只要知道**有沒有選**                                                   | `self.editor.has_selection()`            | 回傳 `True` / `False`，等同 `storage_selection()` 之後判斷 `e > s` |
| 需要**選取的文字**                                                         | `self.doc.text[s:e]`                     | 先用 `storage_selection()` 取得 `s, e`                        |
| 在接到 `selection_changed` 的函式裡（例如 `MainWindow._on_selection_changed`） | 直接用參數 `s, e`                             | 不用另外呼叫                                                    |
| 在接到 `selection_finished` 的函式裡（例如 `_show_quick_label_popup`）         | 自己呼叫 `storage_selection()`               | 參數只有螢幕座標                                                  |

> 範圍一律用 `storage_selection()` 取得，不要用 `textCursor().selectionStart()`，否則遇到有換行的文件，位置會偏掉。

**清除反白**（目前流程中沒有用到；需要時自己呼叫，例如選完術語後想讓反白消失）：

```python
cur = self.editor.textCursor()
cur.clearSelection()
self.editor.setTextCursor(cur)
```

### 想改行為

| 想做的事 | 改哪裡 |
|---|---|
| 放開滑鼠後做別的事（例如「選完解釋 → 跳出概念對話框」） | `MainWindow._show_quick_label_popup` 的開頭；或在 `MainWindow.__init__` 把 `selection_finished` 接到你自己寫的函式 |
| 工具列模式下也要在放開滑鼠時收到通知 | `MainWindow.__init__` 裡的 `if self.use_popup:`，把 `selection_finished` 的接線移到 if 外面 |
| 改狀態列上顯示的選取資訊 | `MainWindow._on_selection_changed` |

---

## 1-3. 按下 Popup 選單裡的標籤按鈕

（`configs/user_preferences.json` 中 `auto_popup_on_selection` 為 `true` 時才會出現）

```
（接 1-2 流程 A）
MainWindow._show_quick_label_popup(global_pos)
   ├─ self.doc 是 None → 直接 return
   ├─ 建立 QMenu
   ├─ 呼叫 self._make_quick_label_widget(menu) → 回傳一排標籤按鈕（依標註模式的標籤自動產生）
   ├─ 加入「複製選取文字」項目（按下 → self.editor.copy()）
   └─ menu.exec(...)          ← 顯示選單；選單關閉之前，程式會停在這一行

使用者按下某個標籤按鈕
   → _make_label_handler(group_id, label_id) 產生的函式
   → MainWindow.apply_label(group_id, label_id)     → 見 1-6
   → menu.close()
```

- 按鈕只把 `group_id`、`label_id` 傳給 `apply_label`，**沒有傳選取範圍**。`apply_label` 會自己呼叫 `storage_selection()` 取得範圍（見 1-6）。
- 想讓 popup 在某些情況下不要跳出來：在 `_show_quick_label_popup` 開頭加條件後 `return`。
- 想改「按下標籤後做什麼」：不用改按鈕，直接改 `apply_label`。

---

## 1-4. 按下工具列的標籤按鈕

（`auto_popup_on_selection` 為 `false` 時才會出現）

```
程式啟動時：
MainWindow.__init__ → MainWindow._build_toolbar() → MainWindow._populate_label_buttons()
                                                      （popup 模式下直接 return，不放按鈕）

使用者按下按鈕
   → _make_label_handler(group_id, label_id) 產生的函式
   → MainWindow.apply_label(group_id, label_id)     → 見 1-6
```

---

## 1-5. 視窗頂端選單列「標註」或標籤快捷鍵（例如 `1`）

這裡的「選單列」是視窗最上方那排文字選單（檔案、編輯、標註…，也就是 `menuBar()`），不是 1-4 的工具列。不管是 popup 模式還是工具列模式，選單列都一定會出現。標籤快捷鍵就設在「標註」選單的項目上，所以即使工具列上沒有標籤按鈕，按 `1` 一樣能標註。

```
程式啟動時：
MainWindow._build_menu() → MainWindow._populate_annotate_menu()
                             （把每個標籤加進「標註」選單，有設定快捷鍵的一併設上）

使用者按下選單項目或快捷鍵
   → _make_label_handler(group_id, label_id) 產生的函式
   → MainWindow.apply_label(group_id, label_id)     → 見 1-6
```

不管是 popup、工具列、選單列、快捷鍵還是右鍵，**最後都會呼叫同一個 `apply_label`**，而且都只傳 `group_id`、`label_id` 兩個參數。

---

## 1-6. `MainWindow.apply_label(group_id, label_id)` 裡做了什麼

本模式下呼叫時一定是 `group_id="entity"`、`label_id="term"`（對應「目標」一節的 `labels`）。

```
apply_label(group_id, label_id)
 │
 ├─ self.doc 是 None → 狀態列提示「請先開啟檔案」，return
 │
 ├─ 【術語模式才會走】
 │   └─ 呼叫 self.editor.has_selection() → True / False
 │   條件：self.mode.id == "term_definition" 且 設定 show_concept_popup 為 true 且 上面回傳 True
 │     └─ 呼叫 self.editor.textCursor().selectedText() → 選取的文字（拿來當對話框的預設值）
 │           ※ 自己寫的話，建議改用 self.doc.text[s:e]（換行字元才會和原文一致）
 │     dlg = ConceptSelectionDialog(self.doc.concepts, default_text=選取文字, parent=self)
 │     └─ 呼叫 dlg.exec()       → True（按確定）/ False（按取消 → 整個 apply_label 直接 return）
 │     └─ 呼叫 dlg.get_result() → (既有概念id, None) / (None, 新概念名稱) / (None, None)
 │     是新概念 → self.doc.concepts[新id] = 名稱，並呼叫 self.concept_panel.refresh(self.doc)
 │
 ├─ 再呼叫一次 self.editor.has_selection()，決定要走 A，還是 B / C
 │
 ├─ 情況 A：沒有選取文字 → 修改游標所在的那個標註
 │     └─ 呼叫 self.editor.annotation_at_cursor() → 標註 id（或 None → 提示後 return）
 │     └─ 呼叫 self.doc.find_annotation(id)       → Annotation 物件
 │     └─ 呼叫 self._confirm_replace_existing_group_label(ann, group_id, label_id) → False 就 return
 │     └─ 呼叫 self._resolve_same_group_overlap(ann.start, ann.end, group_id, exclude_id=ann.id) → False 就 return
 │     ann.labels[group_id] = label_id
 │     ※ 情況 A 不會跳概念選擇器（上面的條件要有反白），概念不會變；模板只有「專業術語」一個標籤，
 │       對已標註文字再套一次等於沒改，所以看起來沒反應。新增第二個 label（2-5）後才會真的改到東西。
 │
 ├─ 有選取文字：
 │     └─ 呼叫 self.editor.storage_selection() → (s, e)     ← 新標註的範圍就是從這裡來的
 │
 │   情況 B：剛好有一個既有標註的範圍等於 (s, e) → 修改那個標註
 │     └─ 同情況 A 的兩個檢查
 │     ann.labels[group_id] = label_id
 │
 │   情況 C：其他情況 → 建立新標註
 │     └─ 呼叫 self._resolve_same_group_overlap(s, e, group_id) → False 就 return
 │            └─ 內部呼叫 self.doc.annotations_in_range_for_group(s, e, group_id) → 重疊的標註 list
 │     ann = Annotation(start=s, end=e, labels={group_id: label_id}, concept_id=...)
 │     └─ 呼叫 self.doc.add_annotation(ann)
 │
 └─ 收尾（見下方）
```

> 📝 `core/models.py` 的 `Document.annotations_in_range_for_group` 裡有一個 **TODO**，請先完成它，重疊檢查才會生效。
>
> 重疊檢查完成後，**任兩個標註的範圍不能重疊**（之後在 2-5 新增的 label 也一樣）。

**收尾：只要改過 `self.doc` 的內容，最後都要呼叫這幾行，畫面才會更新**

```python
self.doc.dirty = True                  # 標題列出現 *、關閉時提醒存檔、自動存檔才會存
self.editor.refresh_highlights()       # 重畫標註顏色
self._refresh_status()                 # 更新狀態列統計
self._update_window_title()            # 更新標題列
self.concept_panel.refresh(self.doc)   # 有改到概念時才需要
```

**想改「按下『專業術語』之後要做什麼」（例如改成兩步驟：先選術語、再選解釋），就改這個函式。** 術語的範圍在這裡用 `storage_selection()` 拿；解釋的範圍則要等使用者第二次選取時（1-2 流程 A）再拿一次。

---

## 1-7. 在編輯器上按右鍵

```
按右鍵 → AnnotationEditor._on_context_menu(pos)          （pos 是右鍵點擊的位置）
           └─ 呼叫 self.cursorForPosition(pos) → 右鍵位置的游標 cursor
           └─ 沒有選取 → 呼叫 self.setTextCursor(cursor)，把文字游標移到右鍵位置（有選取時不動，以免清掉反白）
           └─ 呼叫 self._omap.to_storage(cursor.position()) → 點擊位置在原文中的位置
           └─ 呼叫 self.storage_selection() → (sel_start, sel_end)
           └─ 呼叫 self._doc.annotations_at(位置) → 這個位置上的標註 list
                 有標註 → 取最後一筆的 id 當 ann_id；沒有 → ann_id = None
           → MainWindow._build_context_menu(menu, ann_id, sel_start, sel_end)   ← 三個值都以參數傳進來
                 └─ 沒選取、也沒點在標註上 → 只加一個灰色提示「請先反白文字再標註」，然後 return
                 └─ 呼叫 self.doc.find_annotation(ann_id) → Annotation 物件（用來顯示它的標籤名稱，以及略過它已經套用的標籤）
                 （依序把選單項目加進 menu，見下表）
           → menu 有項目 → menu.exec(...) 顯示選單
```

- 在 `_build_context_menu` 裡，**直接用參數**就好：右鍵點到的標註用 `ann_id`，選取範圍用 `sel_start`、`sel_end`，不需要再呼叫 `storage_selection()`。
- 想拿到「右鍵點到的那筆標註」物件：函式裡已經有 `ann = self.doc.find_annotation(ann_id) if ann_id is not None else None`，可以直接用。但它定義在「提示後 return」和「複製選取文字」之後，如果你的程式碼要加在更前面，就要自己再取一次。

`_build_context_menu` 目前產生的項目，以及按下後呼叫的函式：

| 選單項目 | 什麼時候出現 | 按下後呼叫 |
|---|---|---|
| （灰色）請先反白文字再標註 | 沒有選取、也沒點在標註上時（這時選單只有這一項） | 無 |
| 複製選取文字 | `sel_end > sel_start`（有選取）時 | `self.editor.copy()` |
| （灰色）該標註的標籤名稱 | `ann_id` 不是 `None` 時 | 無 |
| 各標籤（例如「專業術語」） | 有選取，或點在標註上時；**沒有選取時，略過該標註已經套用的標籤**（再套一次不會有任何變化）。模板只有一個標籤，所以沒反白、在已標註文字上右鍵時不會出現「專業術語」 | `apply_label(group_id, label_id)` → 見 1-6 |
| 刪除此處標註 | 有選取，或點在標註上時 | `action_remove_annotation_at_cursor()` → 見 1-10 |

> ⚠️ 選單項目按下後呼叫的 `apply_label`、`action_remove_annotation_at_cursor`，**不會**收到 `ann_id`，而是自己呼叫 `annotation_at_cursor()` 去找「文字游標」所在的標註。沒有選取時，右鍵已經先把文字游標移到點擊處，所以找到的就是右鍵點到的那一個；**有選取時文字游標不會動**，這兩個函式會改以選取範圍為準。如果你新增的項目要針對「右鍵點到的標註」做事，還是建議把 `ann` 直接傳給你的函式（可以照抄的地方見 2-1）。

- 想讓右鍵在某些情況下不顯示某些項目：在 `_build_context_menu` 裡加條件後直接 `return`。目前開頭的「請先反白文字再標註」就是這種寫法；如果 `return` 時選單沒有任何項目，選單就不會跳出來。

---

## 1-8. 用左鍵點擊已標註的文字

**目前點下去沒有任何反應。** `AnnotationEditor` 裡已經宣告了 `annotation_clicked = Signal(str)`，但沒有任何地方 emit 它，也沒有任何函式 connect 它。你需要自己把下面這條流程接起來：

```
放開左鍵 → AnnotationEditor.mouseReleaseEvent(ev)
              └─ 呼叫 self.has_selection() → False（單純點一下，沒有拖選）
              【以下是你要補上的】
              └─ 呼叫 self.cursorForPosition(ev.position().toPoint()) → 再呼叫 self._omap.to_storage(...) → 位置
              └─ 呼叫 self._doc.annotations_at(位置) → 標註 list
              有標註：
              ⇢ emit annotation_clicked(標註 id)
              ⇢ 接到 MainWindow 裡你寫的函式(ann_id)
                    └─ 呼叫 self.doc.find_annotation(ann_id) → Annotation 物件
                    （顯示資訊、高亮解釋段落……見 2-8、2-9）
```

提示：

- 找標註的那三個呼叫，和 1-7 `AnnotationEditor._on_context_menu` 找 `ann_id` 的方式**完全一樣**；有多筆標註時，同樣取最後一筆。
- 程式碼要加在 `mouseReleaseEvent` 裡 `if self.has_selection():` 的 `else` 分支。
- 在 `AnnotationEditor` 裡，文件是 `self._doc`，不是 `self.doc`；還沒開檔時它是 `None`，要先擋掉（見 0-4）。
- `emit`、`connect`、接收函式怎麼寫，可以照抄 2-7 指出的 `FilePanel`（點清單項目 → `emit` → `MainWindow` 裡 `connect`），兩者是同一個模式。

---

## 1-9. 滑鼠停在標註上（tooltip）

```
滑鼠停在編輯區一下下
   → AnnotationEditor.viewportEvent(ev)          (ev.type() == QEvent.ToolTip)
        ├─ self._display_pos_under_mouse(ev.pos())  → 滑鼠下那個字的位置
        ├─ self._doc.annotations_at(storage 位置)   → 蓋住這個字的標註
        └─ QToolTip.showText(..., self._tooltip_text(ann))   ← tooltip 的內容在這裡決定

提示顯示中、滑鼠繼續移動
   → AnnotationEditor.mouseMoveEvent(ev)
        ├─ 還在同一個標註上 → 不動
        ├─ 滑進另一個標註   → 直接換成新內容
        └─ 離開標註         → QToolTip.hideText()
```

每次停留都是當下重算，所以改完標籤再停上去會直接看到新內容。

目前 tooltip 只顯示「群組：標籤」。想多顯示概念名稱，就修改 `_tooltip_text` 回傳的字串（在 editor 裡用 `self._doc.concepts.get(ann.concept_id)` 取得概念名稱）。

> 注意：不能用 `fmt.setToolTip(...)`。標註高亮是用 `ExtraSelection` 畫的，它的 format 只負責繪製，tooltip 屬性不會生效。

---

## 1-10. 刪除標註

```
選單「編輯 → 刪除游標處標註」(Ctrl+D) / 右鍵「刪除此處標註」
   → MainWindow.action_remove_annotation_at_cursor()
        └─ 呼叫 self.editor.storage_selection() → (s, e)
        有選取（e > s）：
           └─ 呼叫 self.doc.annotations_in_range(s, e) → 與範圍重疊的標註 list
           └─ 對每一筆呼叫 self.doc.remove_annotation(a.id)
        沒選取：
           └─ 呼叫 self.editor.annotation_at_cursor() → 游標所在的標註 id（None → 提示後 return）
           └─ 呼叫 self.doc.remove_annotation(ann_id) → True / False
        → 收尾（refresh_highlights、_refresh_status、_update_window_title）
```

刪除標註時，**不會**同時刪掉 `self.doc.concepts` 裡的概念。

---

## 1-11. 存檔、匯出

| 操作 | 流程 | 備註 |
|---|---|---|
| 儲存 (Ctrl+S) | `action_save()` → 呼叫 `io.save_lexa(doc, path, mode)` | 會寫入 `concepts` 與所有標註欄位，不需要修改 |
| 另存新檔 | `action_save_as()` → 呼叫 `io.save_lexa(...)` | |
| 自動存檔（每 60 秒） | `_autosave_tick()` → 呼叫 `io.save_lexa(...)` | 只有 `self.doc.dirty` 為 `True` 時才會存 |
| 匯出 .txt (Ctrl+E) | `action_export()` → 呼叫 `io.export_txt(...)` → 內部呼叫 `io._format_p_line(...)` | 想改匯出格式就改這兩個函式 |

---

## 1-12. 常用函式速查表

最右欄列出「目前程式中哪裡用到它」，可以直接去那裡看真實的用法。

**在 `MainWindow`（app.py）裡呼叫：**

| 想做的事 | 呼叫 | 回傳 | 目前哪裡用到（可參考） |
|---|---|---|---|
| 取得選取範圍 | `self.editor.storage_selection()` | `(start, end)` | `apply_label`、`action_remove_annotation_at_cursor` |
| 有沒有選取 | `self.editor.has_selection()` | `bool` | `apply_label` |
| 取得一段文字 | `self.doc.text[start:end]` | `str` | `_on_selection_changed` |
| 游標所在的標註 | `self.editor.annotation_at_cursor()` | 標註 id 或 `None` | `apply_label`（情況 A）、`action_remove_annotation_at_cursor` |
| 用 id 找標註 | `self.doc.find_annotation(ann_id)` | `Annotation` 或 `None` | `apply_label`、`_build_context_menu` |
| 某個位置上的所有標註 | `self.doc.annotations_at(pos)` | `list[Annotation]` | editor 的 `_on_context_menu`、`annotation_at_cursor` |
| 和某範圍重疊的標註 | `self.doc.annotations_in_range(s, e)` | `list[Annotation]` | `action_remove_annotation_at_cursor` |
| 新增標註 | `self.doc.add_annotation(Annotation(...))` | 無 | `apply_label`（情況 C） |
| 刪除標註 | `self.doc.remove_annotation(ann_id)` | `bool`（有沒有刪到） | `action_remove_annotation_at_cursor` |
| 修改標註欄位 | 直接賦值，例如 `ann.concept_id = cid` | | `apply_label`（情況 A、B） |
| 新增概念 | `cid = "C_" + uuid.uuid4().hex[:8]`<br>`self.doc.concepts[cid] = 名稱` | | `apply_label`（術語模式那段） |
| 用 id 取得概念名稱 | `self.doc.concepts.get(cid)` | 名稱或 `None` | `io.export_txt` |
| 用名稱找概念 id | `next((k for k, v in self.doc.concepts.items() if v == 名稱), None)` | id 或 `None` | 目前沒用到 |
| 更新概念清單 | `self.concept_panel.refresh(self.doc)` | | `load_file`、`apply_label` |
| 重畫標註顏色 | `self.editor.refresh_highlights()` | | `apply_label` 等所有收尾 |
| 捲動並選取某個標註 | `self.editor.jump_to_annotation(ann_id)` | | 目前沒用到 |
| 清除反白 | 見 1-2 的三行寫法 | | 目前沒用到 |
| 狀態列顯示訊息 | `self.status.showMessage(文字, 毫秒)`（填 0 表示一直顯示） | | `apply_label` 等 |
| 判斷目前模式 | `self.mode.id == "term_definition"` | `bool` | `apply_label`、`_switch_mode` |
| 取得標籤資訊 | `self.mode.label(group_id, label_id)` | 有 `.name`、`.color`、`.tag` | `io._format_p_line` |
| 讀取使用者設定 | `self.prefs.behavior.get("鍵", 預設值)` | | `apply_label`、`__init__` |

**在 `AnnotationEditor`（editor.py）裡呼叫：**

| 想做的事 | 呼叫 | 目前哪裡用到（可參考） |
|---|---|---|
| 目前文件 | `self._doc`（不是 `self.doc`） | 整個 editor.py |
| 滑鼠位置 → 文件中的位置 | `self._omap.to_storage(self.cursorForPosition(點).position())` | `_on_context_menu` |
| 文件中的位置 → 編輯器位置（設定游標或畫高亮時用） | `self._omap.to_display(pos)` | `refresh_highlights`、`jump_to_annotation` |
| 發出 signal | `self.xxx.emit(...)` | `mouseReleaseEvent`、`_on_selection_changed` |

---

# 第二部分：GUI 元件怎麼產生、怎麼加

你想加的介面，template 裡幾乎都有一樣或很像的寫法。以下每一節會指出可以照抄的地方，請先找到那段程式碼讀懂，再仿照它寫出你自己的版本。

## 2-1. 在右鍵選單加一個項目

**產生位置：** `MainWindow._build_context_menu(menu, ann_id, sel_start, sel_end)`

**照抄：** 同一個函式最後面「刪除此處標註」那 3 行（建立 `QAction` → `triggered.connect` 接到你的函式 → `menu.addAction`）。

提示：

- 函式中段已經用 `ann_id` 取得 `ann`（右鍵點到的標註，沒點到就是 `None`）。想「只在點到標註時出現」，就把程式碼加在它後面、用 `ann` 判斷；想「只在術語模式出現」，就判斷 `self.mode.id`（`apply_label` 開頭有一樣的判斷）。
- 分隔線、灰色不能按的項目、快捷鍵提示，這個函式裡都有現成的例子：`menu.addSeparator()`、`hint.setEnabled(False)`、`act_copy.setShortcut(...)`。子選單可以參考 `_build_menu` 裡的 `addMenu`。
- 在右鍵選單上 `setShortcut` 只會顯示提示文字，不會變成真的快捷鍵（真的快捷鍵見 2-3、2-10）。
- 項目會依 `addAction` 的順序由上往下排列。
- 按下去時要把 `ann` 傳給你的函式，就要用 `lambda` 包一層，參考 `_build_menu` 裡「下一個檔案」那行。如果是在 `for` 迴圈裡建立多個項目，`lambda` 要用預設參數綁住當下的值，否則每個項目都會拿到最後一個值，參考 `_make_quick_label_widget` 裡 `h=handler` 那行。

---

## 2-2. 在工具列加一個按鈕

**產生位置：** `MainWindow._build_toolbar`（一般按鈕），以及 `MainWindow._populate_label_buttons`（標籤按鈕）

> 按鈕為什麼按了會呼叫你的函式，見第零部分；0-3 有一個從頭到尾的完整按鈕範例。

- **一般按鈕**（兩種模式下都會出現）：照抄 `_build_toolbar` 裡「開啟檔案」那 2 行。
- **彩色按鈕**：照抄 `_populate_label_buttons` 迴圈裡建立按鈕的寫法（`QPushButton` → `setStyleSheet` → `clicked.connect` → `self.toolbar.addWidget`），樣式字串可以參考 `_button_style_for`。注意 `QPushButton` 的 signal 是 `clicked`，不是 `triggered`。
- **標籤按鈕不用手動加**：它們是 `_populate_label_buttons` 依照標註模式 JSON 自動產生的（見 2-5），而且只在 `auto_popup_on_selection: false` 時出現。
- **想之後把按鈕藏起來或顯示出來**：把 `addAction` / `addWidget` 回傳的物件存在 `self` 上，再呼叫 `.setVisible(...)`。`MainWindow.__init__` 裡的 `self.concept_panel.setVisible(...)` 就是一樣的用法。

---

## 2-3. 在選單列加一個項目（含快捷鍵）

**產生位置：** `MainWindow._build_menu`

**照抄：** 「刪除游標處標註」（`self.act_remove_ann`）那 4 行。

- 快捷鍵用 `self.prefs.app_shortcut(名稱, 預設值)` 取得，使用者就能在設定檔覆寫。加在選單列上的快捷鍵，在整個視窗裡都有效。
- 要放進哪個選單，就 `addAction` 到那個選單：`m_file`、`m_edit` 是現有的選單；想開一個新的選單，參考同一個函式裡的 `mb.addMenu(...)`。
- 如果這個項目只在開檔後才能用，參考 `MainWindow._update_actions`，它負責在沒開檔時把項目變灰。

---

## 2-4. 在 Popup 選單加按鈕或項目

**產生位置：** `MainWindow._show_quick_label_popup`（選單本體）、`MainWindow._make_quick_label_widget`（那一排標籤按鈕）

- 加一般選單項目：在 `_show_quick_label_popup` 裡仿照「複製選取文字」，用 `QAction` + `menu.addAction(...)`。
- 在標籤那一排加按鈕：在 `_make_quick_label_widget` 裡建立 `QPushButton`，再 `row.addWidget(btn)`。按下後記得呼叫 `host_menu.close()` 關閉選單。

---

## 2-5. 新增或修改標籤

**不用改程式碼**，改 `configs/annotation_modes/term_definition.json` 的 `labels`：

```json
{ "id": "term", "name": "專業術語", "tag": "Term", "color": "#FFE082", "shortcut": "1" }
```

| 欄位         | 用途                                                     |
| ---------- | ------------------------------------------------------ |
| `id`       | 存進 `Annotation.labels` 的值；`apply_label` 收到的 `label_id` |
| `name`     | 按鈕與選單上顯示的文字                                            |
| `tag`      | 匯出 .txt 時用的標籤字串                                        |
| `color`    | 按鈕與高亮的顏色                                               |
| `shortcut` | 快捷鍵                                                    |

改完重新啟動程式後，工具列、popup、選單列、右鍵選單都會自動出現新的標籤。

> ⚠️ 新增的 label 按下去一樣會呼叫 `apply_label`：會跳概念對話框、經過重疊檢查（和既有標註不能重疊，見 1-6），最後寫進 `labels`。
> 如果加這個 label 只是想要一顆「解釋」之類的按鈕，請在 `apply_label` 最前面判斷 `label_id`，改呼叫你自己的函式後直接 `return`；或改用 2-2 / 2-4 的一般按鈕。

---

## 2-6. 概念對話框不夠用時怎麼改

**位置：** `widgets/concept_panel.py` → `ConceptSelectionDialog`
**唯一的呼叫端：** `MainWindow.apply_label`

**目前的結構：**

```
ConceptSelectionDialog.__init__(concepts, default_text, parent)
   layout = QVBoxLayout(self)                 ← 元件依 addWidget 的順序由上往下排列
   ├─ QLabel("1. 從現有概念選擇：")
   ├─ self.list_widget   (QListWidget)        ← 列出既有概念
   ├─ QLabel("2. 或直接輸入新概念：")
   ├─ self.input_edit    (QLineEdit)          ← 預設填入選取的文字
   └─ btn_layout: self.btn_ok → accept() / self.btn_cancel → reject()

get_result() → (既有id, None) / (None, 新名稱) / (None, None)    ← 只讀 self.input_edit
```

### (a) 想多一個欄位（例如「上位概念」）

要改三個地方，每個地方在 template 裡都有可以照抄的寫法：

1. **`__init__`**：「從既有概念選一個，或輸入新的」，對話框裡現有的概念欄位已經做過一次了：`QLabel` 標題 → `list_widget` 列出既有概念，並用 `_concept_map` 記住「名稱 → id」→ `input_edit` 讓使用者輸入 → 最後用 `itemClicked` 把點到的項目填進輸入框。新欄位可以照這一整套再做一份。
   - 新元件要加在 `btn_layout` 之前，否則會排到按鈕下面。
   - 想改用下拉選單，或「打字時自動篩選」，可以查 `QComboBox`、`QCompleter`。記得在檔案開頭的 import 補上。
2. **`get_result`**：目前只讀 `self.input_edit`，但已經會判斷「選到既有概念 → 回傳 id」還是「自己輸入 → 回傳新名稱」。新欄位照同樣的邏輯再判斷一次，再把結果加進回傳值。
3. **`apply_label`**：`dlg.get_result()` 的回傳格式改了，接收的那一行要跟著改。
   - 新欄位如果是新名稱，就照抄同一段的「建立新概念」（產生 id → 寫進 `self.doc.concepts` → `self.concept_panel.refresh`）。
   - `apply_label` 裡有三個地方會寫入 `concept_id`（兩處更新既有標註、一處建立新的 `Annotation`），新欄位也要在這三個地方一起處理。

### (b) 想在對話框裡顯示更多資訊（例如術語文字、解釋文字，或編輯時的預設值）

照抄 `default_text` 的做法，它是「從呼叫端帶資料進對話框」的現成範例：

- `apply_label` 先取得選取的文字（`selected_text`），建立對話框時當作參數傳進去。
- `__init__` 的參數列有 `default_text`，再用 `self.input_edit.setText(default_text)` 填進元件。

想多帶什麼資料進來，就照這條路多加一個參數，呼叫端也要一起改。要顯示只能看、不能改的文字，可以參考 `AnnotationEditor.__init__` 裡的 `setReadOnly(True)`（編輯區本身就是一個唯讀的文字框）。

### (c) 想在按「確定」時檢查輸入

- `btn_ok` 按下去呼叫的是 `self.accept`（`QDialog` 內建的方法），所以要在類別裡覆寫 `accept`。
- 「檢查沒過就中止、通過才交給 Qt 繼續」的模式，可以參考 `MainWindow.closeEvent`：沒通過就直接 `return`，通過才呼叫 `super()` 的同名方法。`accept` 裡沒有呼叫 `super().accept()`，對話框就不會關閉。
- 跳警告視窗的寫法 template 裡到處都有，例如 `MainWindow._warn_if_group_conflicts` 裡的 `QMessageBox.warning`（`concept_panel.py` 已經 import 了 `QMessageBox`）。

### (d) 想多一個按鈕（例如「回上一步」）

- 按鈕本身照抄 `btn_cancel` 那幾行（建立 `QPushButton` → `clicked.connect` → `btn_layout.addWidget`）。
- `exec()` 只會回傳 True（`accept`）或 False（`reject`），分不出「取消」和「回上一步」。可以在按鈕的處理函式裡先設一個屬性當作記號，再呼叫 `self.reject()` 關閉對話框；呼叫端在 `dlg.exec()` 之後讀這個屬性，決定下一步要做什麼。

### (e) 想整個重寫

可以在 `concept_panel.py` 新增一個類別，照抄 `ConceptSelectionDialog` 的骨架（繼承 `QDialog`、在 `__init__` 排版、提供一個取結果的方法）。再修改 `app.py` 開頭的 `from .widgets.concept_panel import ...`，以及 `apply_label` 裡建立對話框的那幾行。

---

## 2-7. 概念清單（右下角側欄）

**位置：** `widgets/concept_panel.py` → `ConceptSidebar`

- 清單內容在 `refresh(doc)` 裡產生，每次呼叫都會清空後重新列出 `doc.concepts`。
- `concept_clicked = Signal(str)` 已經宣告，但還沒接上任何東西。

想讓「點擊概念」有反應，**照抄 `widgets/file_panel.py` → `FilePanel`**。它是同一個模式的完整範例：點清單項目 → 發出帶資料的 signal → `MainWindow` 接起來。

| 要做的事 | `FilePanel` 裡對應的地方 |
|---|---|
| 讓每個項目記住自己的 id | `refresh` 裡用 `QListWidgetItem` 建立項目，再用 `setData(Qt.UserRole, ...)` 存資料 |
| 點擊時取出 id、發出 signal | `__init__` 把清單的 signal 接到 `_on_item_activated`，它用 `item.data(Qt.UserRole)` 取出資料後 `emit` |
| 在 `MainWindow` 接到你的函式 | `MainWindow.__init__` 裡 `self.file_panel.file_open_requested.connect(...)` 那行 |

- `FilePanel` 接的是 `itemActivated`（雙擊或按 Enter 才觸發）；想要單擊就有反應，改用 `itemClicked`（`ConceptSelectionDialog` 裡有用到）。
- 記得在 `concept_panel.py` 開頭 import `QListWidgetItem`。

---

## 2-8. 顯示一個小資訊視窗（例如點擊標註時）

- **最簡單：用 tooltip。** 照抄 `AnnotationEditor.viewportEvent` 裡的 `QToolTip.showText(...)`。想顯示在滑鼠目前的位置，可以查 `QCursor.pos()`（在 `PySide6.QtGui`）。
- **想自訂內容、點外面會自動關閉：** 參考 `MainWindow._show_quick_label_popup`。它用 `QMenu` 當外框，再用 `QWidgetAction` 把自己做的元件（`_make_quick_label_widget` 回傳的 `QFrame`）塞進去，最後用 `menu.exec(位置)` 顯示。把裡面的按鈕換成 `QLabel`，就是一個資訊視窗。
- **想把視窗放在「某個標註」旁邊，而不是滑鼠旁邊：**
  - 建立一個 cursor 並設到標註的位置：參考 `AnnotationEditor.jump_to_annotation` 的寫法（`ann.start` 要先經過 `_omap.to_display` 轉換）。
  - 取得那個位置在畫面上的方框：參考 `_display_pos_under_mouse` 裡的 `cursorRect`。
  - `cursorRect` 回傳的是編輯區（viewport）裡的座標，`exec` / `showText` 要的是螢幕座標，要再用 `viewport().mapToGlobal(...)` 轉換。

---

## 2-9. 在編輯器上畫額外的高亮（例如標示解釋段落）

**位置：** `AnnotationEditor.refresh_highlights`

這個函式每次都會重新產生所有高亮，然後用 `self.setExtraSelections(selections)` 一次套用。想多畫一段，可以拆成三步：

1. **記住要畫哪一段**：在 `AnnotationEditor.__init__` 加一個屬性。可以參考 `_tooltip_ann_ids`，它也是用來「記住目前狀態」的屬性。
2. **把它畫出來**：在 `refresh_highlights` 裡，照抄 `for ann in ...` 迴圈內建立一個 `ExtraSelection` 的那幾行，範圍換成你記住的那一段，再 `append` 進 `selections`。顏色的設法參考 `_apply_format_for_labels` 最後的 `fmt.setBackground(...)`。
3. **讓 `MainWindow` 能開關它**：在 `AnnotationEditor` 寫方法去改那個屬性，改完呼叫 `self.refresh_highlights()` 重畫（`attach` 的結尾也是這樣做）。`MainWindow` 再透過 `self.editor.你的方法(...)` 呼叫。

- 範圍存的是 storage offset，畫之前要用 `_omap.to_display` 轉換（迴圈裡就是這樣做的）。
- `selections` 列表中越後面的項目會畫在越上層。
- 不要在其他地方另外呼叫 `setExtraSelections`，否則下次 `refresh_highlights()` 時會被蓋掉。

---

## 2-10. 其他常用介面

| 想做的事 | template 裡可以抄的地方 | 放在哪裡 |
|---|---|---|
| 狀態列訊息 | `apply_label` 開頭的 `self.status.showMessage(...)`；第二個參數是顯示幾毫秒，`0` 表示一直顯示 | `MainWindow` 任何地方 |
| 是 / 否確認 | `MainWindow._confirm_replace_existing_group_label` 裡的 `QMessageBox.question` | 同上 |
| 警告 / 提示 | `_warn_if_group_conflicts` 裡的 `QMessageBox.warning`、`action_export` 裡的 `QMessageBox.information` | 同上 |
| 改變滑鼠游標 | `_populate_label_buttons` 裡的 `btn.setCursor(...)`；要改編輯區的游標，對象換成 `self.editor.viewport()`，還原用 `Qt.IBeamCursor` | 同上 |
| 浮在編輯器上的提示字 | template 沒有現成範例：建立 `QLabel` 時把 `self.editor` 當作 parent，它就會浮在編輯器上，之後用 `show()` / `hide()` / `move()` 控制 | 在 `__init__` 建立 |
| 全域快捷鍵（例如 Esc） | template 沒有現成範例（`editor.py` 只 import 了 `QShortcut`，沒有用到）：查 `QShortcut`、`QKeySequence`，它的 signal 是 `activated`。如果這個快捷鍵也想出現在選單上，用 2-3 的做法即可 | `MainWindow._setup_app_shortcuts`（目前是空的）；`QShortcut` 要從 `PySide6.QtGui` import |
| 新增一個使用者設定 | 讀取：照抄 `apply_label` 裡的 `self.prefs.behavior.get("show_concept_popup", True)`<br>預設值：照抄 `core/config.py` → `DEFAULT_PREFERENCES` 裡 `show_concept_popup` 那行 | |

---

# 附錄

## 已知問題
`core/io.py` → `export_txt` 的第 2 步中，變數 `seg_concept_id` 沒有在每一段開始時重設。文件開頭如果沒有帶概念的標註，匯出時會出現 `UnboundLocalError`。如果你遇到這個錯誤，請從這裡修起。

## 除錯
- 執行：在專案根目錄執行 `python main.py`。
- 想知道某個函式有沒有被呼叫：在函式第一行加 `log.info("進入 xxx")`（app.py、editor.py 開頭都有 `log`），然後從選單「說明 → 開啟 log 資料夾」查看。
- 檢查資料：存成 `.lexa` 後用文字編輯器打開，看看欄位是否正確。

## 驗收清單
- [ ] `annotations_in_range_for_group` 的 TODO 已完成
- [ ] 新建的標註：`doc.text[start:end]` 是術語，`doc.text[explanation_start:explanation_end]` 是解釋
- [ ] 用判決 JSON（含換行）測試，範圍仍然正確
- [ ] `concept_id`、`broader_concept_id` 都存在於 `doc.concepts`；選擇既有概念時不會重複建立
- [ ] 存檔、關閉、重新開啟後，資料一致
- [ ] popup 模式和工具列模式都能完成標註
- [ ] 點擊已標註的術語可以看到概念資訊
- [ ] 中途取消後，不會留下多餘的高亮或提示
