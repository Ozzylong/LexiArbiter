"""LexiArbiter「選項」設定對話框。

提供 GUI 介面修改 user_preferences.json，避免使用者必須手動編輯 JSON 檔。
標註模式（annotation_modes/*.json）僅提供唯讀預覽與重新掃描；模式結構編輯
有意排除，避免一般標註者誤改造成既有標註失效。

對話框使用 working copy 模式：所有修改先寫到 deepcopy 的 dict，按下「儲存」
通過衝突檢查後才覆蓋 prefs.data 並 save() 到磁碟；按「取消」完全不影響。
"""

from __future__ import annotations

import logging
import os
import sys
from copy import deepcopy
from typing import Optional

log = logging.getLogger(__name__)

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFontComboBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QSplitter, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
    QKeySequenceEdit,
)

from ..core import config as cfgmod
from ..core.config import (
    AnnotationMode, GroupDef, LabelDef, UserPreferences, list_annotation_modes,
)


# ---------------------------------------------------------------------------
# 對話框主體
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    """主「選項」對話框：左側類別清單 + 右側 QStackedWidget 詳細頁。"""

    def __init__(self, prefs: UserPreferences, mode: AnnotationMode,
                 modes: list[AnnotationMode], parent=None):
        super().__init__(parent)
        self.setWindowTitle("選項")
        self.resize(820, 560)

        self._prefs = prefs
        self._mode = mode
        self._working_modes: list[AnnotationMode] = list(modes)
        # working copy：所有修改在這裡進行，accept 時才寫回 prefs.data
        self._working_data: dict = deepcopy(prefs.data)

        # 給 MainWindow 用的回傳狀態
        self._pending_mode_id: Optional[str] = None
        self._did_rescan: bool = False

        # ----- 版面 -----
        self._nav = QListWidget()
        self._nav.setMaximumWidth(160)
        self._stack = QStackedWidget()

        self._page_general = _GeneralPage(self._working_data)
        self._page_behavior = _BehaviorPage(self._working_data)
        self._page_app_shortcuts = _AppShortcutsPage(
            self._working_data,
            # 從 MainWindow class attr 拿綁定列表，避免重複定義
            parent.__class__._APP_SHORTCUT_BINDINGS if parent else [],
        )
        self._page_label_shortcuts = _LabelShortcutsPage(
            self._working_data, self._mode,
        )
        self._page_modes = _ModesPage(self)

        for title, page in [
            ("一般", self._page_general),
            ("行為", self._page_behavior),
            ("應用程式快捷鍵", self._page_app_shortcuts),
            ("標註快捷鍵", self._page_label_shortcuts),
            ("標註模式", self._page_modes),
        ]:
            self._nav.addItem(title)
            self._stack.addWidget(page)

        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._nav)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([160, 660])

        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.button(QDialogButtonBox.Save).setText("儲存")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        layout.addWidget(button_box)

    # ------------------------------------------------ 給 MainWindow 用的查詢 API

    @property
    def did_rescan(self) -> bool:
        return self._did_rescan

    @property
    def refreshed_modes(self) -> list[AnnotationMode]:
        return self._working_modes

    @property
    def pending_active_mode_id(self) -> Optional[str]:
        return self._pending_mode_id

    # ------------------------------------------------ ModesPage 回呼介面

    def request_rescan_modes(self) -> list[AnnotationMode]:
        """ModesPage 點「重新掃描」時呼叫。回傳新的 modes 清單。"""
        try:
            new_modes = list_annotation_modes()
        except Exception:
            log.error("重新掃描標註模式失敗", exc_info=True)
            QMessageBox.critical(self, "錯誤", "重新掃描失敗，請查看 log。")
            return self._working_modes
        self._working_modes = new_modes
        self._did_rescan = True
        return new_modes

    def request_set_active_mode(self, mode_id: str) -> None:
        """ModesPage 點「設為使用中模式」時呼叫。實際切換在 accept 後由 MainWindow 處理。"""
        self._pending_mode_id = mode_id
        self._working_data["active_annotation_mode"] = mode_id

    # ------------------------------------------------ 儲存流程

    def accept(self):
        # 1) 收集每頁變更到 working_data
        self._page_general.flush()
        self._page_behavior.flush()
        self._page_app_shortcuts.flush()
        self._page_label_shortcuts.flush()
        # ModesPage 不寫入 working_data（active_mode 已經在 request_set_active_mode 寫入了）

        # 2) 衝突檢查
        conflicts = self._collect_conflicts()
        if conflicts:
            msg = "下列快捷鍵有衝突，請修正後再儲存：\n\n" + "\n".join(
                f"• {key}：{', '.join(owners)}" for key, owners in conflicts.items()
            )
            QMessageBox.warning(self, "快捷鍵衝突", msg)
            return  # 不關閉對話框

        # 3) 寫回 prefs 並 save
        try:
            self._prefs.data.clear()
            self._prefs.data.update(self._working_data)
            self._prefs.save()
        except Exception as e:
            log.error("儲存偏好設定失敗", exc_info=True)
            QMessageBox.critical(self, "儲存失敗", f"無法寫入偏好設定檔：\n{e}")
            return

        super().accept()

    # ------------------------------------------------ 衝突偵測

    def _collect_conflicts(self) -> dict[str, list[str]]:
        """檢查 working_data 內的所有快捷鍵設定，回傳衝突 dict。

        Key 為衝突的快捷鍵字串，value 為使用該按鍵的所有動作中文名稱列表。
        空字串會被忽略。app shortcut 與 label shortcut 跨類別也會比對。
        """
        # 收集 (display, owner_label)
        items: list[tuple[str, str]] = []

        # App shortcuts（含 prefs override 的最終值）
        app_ov = self._working_data.get("shortcut_overrides", {}).get("_app", {})
        bindings = self._page_app_shortcuts._bindings
        for _attr, name, default, label in bindings:
            seq = app_ov.get(name, default) or ""
            seq = QKeySequence(seq).toString()  # 正規化
            if seq:
                items.append((seq, f"應用：{label}"))

        # Label shortcuts（含 prefs override 的最終值）
        label_ov = self._working_data.get("shortcut_overrides", {})
        for g in self._mode.groups:
            for lb in g.labels:
                key = f"{g.id}.{lb.id}"
                seq = label_ov.get(key, lb.shortcut) or ""
                seq = QKeySequence(seq).toString()
                if seq:
                    items.append((seq, f"標註：{g.name} / {lb.name}"))

        # 找重複
        groups: dict[str, list[str]] = {}
        for seq, owner in items:
            groups.setdefault(seq, []).append(owner)
        return {k: v for k, v in groups.items() if len(v) > 1}


# ---------------------------------------------------------------------------
# 一般頁
# ---------------------------------------------------------------------------

class _GeneralPage(QWidget):
    """字型、字級、行距、主題、顯示段落分隔。"""

    def __init__(self, working_data: dict):
        super().__init__()
        self._data = working_data
        ui = working_data.setdefault("ui", {})

        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignRight)

        self._font = QFontComboBox()
        cur_family = ui.get("font_family", "Microsoft JhengHei UI")
        self._font.setCurrentFont(QFont(cur_family))
        layout.addRow("字型：", self._font)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 32)
        self._font_size.setValue(int(ui.get("font_size", 14)))
        self._font_size.setSuffix(" pt")
        layout.addRow("字級：", self._font_size)

        self._line_spacing = QDoubleSpinBox()
        self._line_spacing.setRange(1.0, 3.0)
        self._line_spacing.setSingleStep(0.1)
        self._line_spacing.setDecimals(1)
        self._line_spacing.setValue(float(ui.get("line_spacing", 1.5)))
        layout.addRow("行距倍率：", self._line_spacing)

        self._theme = QComboBox()
        self._theme.addItem("淺色 (light)", userData="light")
        cur_theme = ui.get("theme", "light")
        idx = self._theme.findData(cur_theme)
        if idx < 0:
            idx = 0
        self._theme.setCurrentIndex(idx)
        layout.addRow("主題：", self._theme)

        self._show_para = QCheckBox("顯示段落分隔提示")
        self._show_para.setChecked(bool(ui.get("show_paragraph_breaks", True)))
        layout.addRow("", self._show_para)

    def flush(self):
        ui = self._data.setdefault("ui", {})
        ui["font_family"] = self._font.currentFont().family()
        ui["font_size"] = int(self._font_size.value())
        ui["line_spacing"] = float(self._line_spacing.value())
        ui["theme"] = self._theme.currentData() or "light"
        ui["show_paragraph_breaks"] = self._show_para.isChecked()


# ---------------------------------------------------------------------------
# 行為頁
# ---------------------------------------------------------------------------

class _BehaviorPage(QWidget):
    """切換模式時警告未存檔、匯出時警告群組未填齊。"""

    def __init__(self, working_data: dict):
        super().__init__()
        self._data = working_data
        b = working_data.setdefault("behavior", {})

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._confirm_unsaved = QCheckBox("切換模式或關閉時，若有未儲存的標註則先詢問")
        self._confirm_unsaved.setChecked(bool(b.get("confirm_unsaved_on_switch", True)))
        layout.addWidget(self._confirm_unsaved)

        self._warn_partial = QCheckBox("匯出 .txt 時，若有段落未填齊所有群組則顯示警告")
        self._warn_partial.setChecked(bool(b.get("warn_partial_groups_on_export", True)))
        layout.addWidget(self._warn_partial)

        layout.addStretch()

    def flush(self):
        b = self._data.setdefault("behavior", {})
        b["confirm_unsaved_on_switch"] = self._confirm_unsaved.isChecked()
        b["warn_partial_groups_on_export"] = self._warn_partial.isChecked()


# ---------------------------------------------------------------------------
# 應用程式快捷鍵頁
# ---------------------------------------------------------------------------

class _ShortcutRow(QFrame):
    """單一快捷鍵設定列：標籤 + QKeySequenceEdit + 重設按鈕 + 預設值提示。"""

    def __init__(self, display_name: str, default_seq: str, current_seq: str,
                 reset_text: str = "重設"):
        super().__init__()
        self._default = default_seq
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        name_lbl = QLabel(display_name)
        name_lbl.setMinimumWidth(140)
        layout.addWidget(name_lbl)

        self._edit = QKeySequenceEdit()
        if current_seq:
            self._edit.setKeySequence(QKeySequence(current_seq))
        layout.addWidget(self._edit, 1)

        default_lbl = QLabel(f"預設：{default_seq}" if default_seq else "預設：(無)")
        default_lbl.setStyleSheet("color: #607D8B;")
        layout.addWidget(default_lbl)

        btn_reset = QPushButton(reset_text)
        btn_reset.clicked.connect(self._on_reset)
        layout.addWidget(btn_reset)

    def _on_reset(self):
        # 將輸入框清空，flush 時會被視為「使用預設」
        self._edit.clear()

    def value(self) -> str:
        """回傳目前 QKeySequenceEdit 的字串表示（空字串代表清空，使用預設）。"""
        return self._edit.keySequence().toString()


class _AppShortcutsPage(QWidget):
    """為 _APP_SHORTCUT_BINDINGS 中每個動作提供 QKeySequenceEdit 設定列。"""

    def __init__(self, working_data: dict, bindings: list[tuple[str, str, str, str]]):
        super().__init__()
        self._data = working_data
        self._bindings = bindings
        self._rows: dict[str, _ShortcutRow] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        hint = QLabel(
            "清空欄位可恢復為預設值。\n"
            "若與標註快捷鍵衝突，按「儲存」時會被攔下。"
        )
        hint.setStyleSheet("color: #607D8B;")
        layout.addWidget(hint)

        ov = working_data.get("shortcut_overrides", {}).get("_app", {})
        for _attr, name, default, label in bindings:
            current = ov.get(name, default)
            row = _ShortcutRow(label, default, current)
            self._rows[name] = row
            layout.addWidget(row)

        layout.addStretch()

    def flush(self):
        ov_root = self._data.setdefault("shortcut_overrides", {})
        ov_app = ov_root.setdefault("_app", {})
        for _attr, name, default, _label in self._bindings:
            row = self._rows[name]
            value = row.value()
            if not value or value == default:
                # 與預設相同（或清空）→ 移除 override，讓 app_shortcut() 走 default
                ov_app.pop(name, None)
            else:
                ov_app[name] = value


# ---------------------------------------------------------------------------
# 標註快捷鍵頁
# ---------------------------------------------------------------------------

class _LabelShortcutsPage(QWidget):
    """依目前 active mode 動態產生：每個 group 一個 QGroupBox，內含每個 label 的設定列。"""

    def __init__(self, working_data: dict, mode: AnnotationMode):
        super().__init__()
        self._data = working_data
        self._mode = mode
        # key = "{group_id}.{label_id}" → row
        self._rows: dict[str, _ShortcutRow] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        hint = QLabel(
            f"目前使用中模式：{mode.name}（{mode.id}）\n"
            "清空欄位可恢復為模式檔案內的預設快捷鍵。"
        )
        hint.setStyleSheet("color: #607D8B;")
        layout.addWidget(hint)

        ov = working_data.get("shortcut_overrides", {})

        for g in mode.groups:
            box = QGroupBox(f"{g.name}（{g.id}）")
            box_layout = QVBoxLayout(box)
            box_layout.setSpacing(4)
            for lb in g.labels:
                key = f"{g.id}.{lb.id}"
                default = lb.shortcut or ""
                current = ov.get(key, default)
                row = _ShortcutRow(lb.name, default, current)
                self._rows[key] = row
                box_layout.addWidget(row)
            layout.addWidget(box)

        layout.addStretch()

    def flush(self):
        ov_root = self._data.setdefault("shortcut_overrides", {})
        for g in self._mode.groups:
            for lb in g.labels:
                key = f"{g.id}.{lb.id}"
                row = self._rows[key]
                value = row.value()
                default = lb.shortcut or ""
                if not value or value == default:
                    # 清空或與 mode 預設相同 → 移除 override
                    ov_root.pop(key, None)
                else:
                    ov_root[key] = value


# ---------------------------------------------------------------------------
# 標註模式頁（唯讀預覽 + 重新掃描 + 設為使用中）
# ---------------------------------------------------------------------------

class _ModesPage(QWidget):
    """列出所有標註模式（唯讀）；按鈕：設為使用中、重新掃描資料夾、開啟模式資料夾。"""

    def __init__(self, dialog: SettingsDialog):
        super().__init__()
        self._dialog = dialog

        layout = QVBoxLayout(self)

        hint = QLabel(
            "此頁僅供瀏覽與切換目前使用的標註模式。\n"
            "要修改模式內容（群組、標籤、tag、匯出格式），請手動編輯模式資料夾內的 .json 檔，\n"
            "並回到此頁按「重新掃描資料夾」。"
        )
        hint.setStyleSheet("color: #607D8B;")
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Vertical)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._list)

        self._preview = QTextBrowser()
        self._preview.setOpenExternalLinks(False)
        splitter.addWidget(self._preview)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([180, 360])
        layout.addWidget(splitter)

        buttons_row = QHBoxLayout()
        self._btn_set_active = QPushButton("設為使用中模式")
        self._btn_set_active.clicked.connect(self._on_set_active)
        self._btn_rescan = QPushButton("重新掃描資料夾")
        self._btn_rescan.clicked.connect(self._on_rescan)
        self._btn_open_dir = QPushButton("開啟模式資料夾")
        self._btn_open_dir.clicked.connect(self._on_open_dir)
        buttons_row.addWidget(self._btn_set_active)
        buttons_row.addWidget(self._btn_rescan)
        buttons_row.addWidget(self._btn_open_dir)
        buttons_row.addStretch()
        layout.addLayout(buttons_row)

        self._refresh_list()

    # ------- 重建列表

    def _refresh_list(self):
        self._list.clear()
        active_id = (self._dialog.pending_active_mode_id
                     or self._dialog._mode.id)
        modes = self._dialog._working_modes
        for m in modes:
            mark = "✓ " if m.id == active_id else "    "
            item = QListWidgetItem(f"{mark}{m.name}    ({m.id})")
            item.setData(Qt.UserRole, m.id)
            self._list.addItem(item)
        if modes:
            self._list.setCurrentRow(0)

    def _selected_mode(self) -> Optional[AnnotationMode]:
        item = self._list.currentItem()
        if item is None:
            return None
        mode_id = item.data(Qt.UserRole)
        for m in self._dialog._working_modes:
            if m.id == mode_id:
                return m
        return None

    def _on_selection_changed(self, _row: int):
        m = self._selected_mode()
        if m is None:
            self._preview.clear()
            return
        self._preview.setHtml(_render_mode_html(m))

    # ------- 按鈕行為

    def _on_set_active(self):
        m = self._selected_mode()
        if m is None:
            return
        self._dialog.request_set_active_mode(m.id)
        self._refresh_list()

    def _on_rescan(self):
        new_modes = self._dialog.request_rescan_modes()
        self._refresh_list()
        QMessageBox.information(
            self, "已重新掃描",
            f"目前共讀取到 {len(new_modes)} 個標註模式。"
        )

    def _on_open_dir(self):
        d = cfgmod.annotation_modes_dir()
        try:
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(d)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f"open '{d}'")
            else:
                os.system(f"xdg-open '{d}'")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"無法開啟資料夾：\n{e}")


# ---------------------------------------------------------------------------
# Mode 預覽 HTML
# ---------------------------------------------------------------------------

def _render_mode_html(m: AnnotationMode) -> str:
    """將 AnnotationMode 渲染成唯讀 HTML 預覽，QTextBrowser 顯示用。"""
    parts: list[str] = []
    parts.append(f"<h3>{_esc(m.name)}　<span style='color:#607D8B;'>({_esc(m.id)})</span></h3>")
    if m.description:
        parts.append(f"<p>{_esc(m.description)}</p>")
    if m.file_path:
        parts.append(
            f"<p style='color:#607D8B;'>來源：{_esc(str(m.file_path))}</p>"
        )

    parts.append("<h4>標註群組</h4>")
    for g in m.groups:
        parts.append(
            f"<p><b>{_esc(g.name)}</b>　"
            f"<span style='color:#607D8B;'>{_esc(g.id)}, role={_esc(g.role)}</span></p>"
        )
        if g.description:
            parts.append(f"<p style='margin-left:1em;'>{_esc(g.description)}</p>")
        parts.append(
            "<table border='1' cellspacing='0' cellpadding='4' "
            "style='border-collapse: collapse; margin-left:1em;'>"
        )
        parts.append(
            "<tr><th>標籤</th><th>id</th><th>tag</th>"
            "<th>顏色</th><th>預設快捷鍵</th></tr>"
        )
        for lb in g.labels:
            color_cell = (
                f"<span style='display:inline-block;width:14px;height:14px;"
                f"background:{_esc(lb.color)};border:1px solid #455A64;'></span>"
                f" {_esc(lb.color)}"
                if lb.color
                else "<span style='color:#90A4AE;'>(無)</span>"
            )
            parts.append(
                f"<tr><td>{_esc(lb.name)}</td>"
                f"<td>{_esc(lb.id)}</td>"
                f"<td>{_esc(lb.tag)}</td>"
                f"<td>{color_cell}</td>"
                f"<td>{_esc(lb.shortcut or '')}</td></tr>"
            )
        parts.append("</table>")

    parts.append("<h4>匯出設定</h4>")
    e = m.export
    parts.append(
        "<table border='1' cellspacing='0' cellpadding='4' "
        "style='border-collapse: collapse;'>"
    )
    rows = [
        ("format", e.format),
        ("tag_order", ", ".join(e.tag_order)),
        ("tag_separator", repr(e.tag_separator)),
        ("wrapper_open", repr(e.wrapper_open)),
        ("wrapper_close", repr(e.wrapper_close)),
        ("field_separator", repr(e.field_separator)),
        ("include_unannotated", str(e.include_unannotated)),
        ("require_all_groups", str(e.require_all_groups)),
    ]
    for key, val in rows:
        parts.append(f"<tr><td><b>{_esc(key)}</b></td><td>{_esc(val)}</td></tr>")
    parts.append("</table>")

    return "".join(parts)


def _esc(s) -> str:
    """簡易 HTML 跳脫，避免 mode 內容內含 < > & 時破版。"""
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;"))
