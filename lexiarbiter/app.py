"""LexiArbiter main window."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QIcon, QKeySequence, QPainter, QPalette,
    QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QMessageBox, QPushButton, QSplitter, QStatusBar, QToolBar, QVBoxLayout,
    QWidget,
)

from . import __app_name__, __version__
from .core import config as cfgmod
from .core import io as iomod
from .core.config import (
    AnnotationMode, GroupDef, LabelDef, UserPreferences,
    list_annotation_modes, load_annotation_mode,
)
from .core.models import Annotation, Document
from .widgets.editor import AnnotationEditor
from .widgets.file_panel import FilePanel


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _swatch_icon(hex_color: Optional[str], size: int = 16) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    if hex_color:
        c = QColor(hex_color)
    else:
        c = QColor("#90A4AE")
    p.setBrush(c)
    p.setPen(QColor("#37474F"))
    p.drawRoundedRect(2, 2, size - 4, size - 4, 3, 3)
    p.end()
    return QIcon(pix)


# ---------------------------------------------------------------------------
# main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} - 法律文件標註工具")
        self.resize(1280, 820)

        self.prefs: UserPreferences = UserPreferences.load()
        self.modes: list[AnnotationMode] = list_annotation_modes()
        self.mode: AnnotationMode = self._select_initial_mode()

        self.doc: Optional[Document] = None

        # central editor + file panel
        self.editor = AnnotationEditor()
        self.editor.set_context_menu_builder(self._build_context_menu)
        self.editor.selection_changed.connect(self._on_selection_changed)

        self.file_panel = FilePanel()
        self.file_panel.file_open_requested.connect(self._handle_file_open_requested)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.editor)
        splitter.addWidget(self.file_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([900, 280])

        self.setCentralWidget(splitter)

        self._build_toolbar()
        self._build_menu()
        self._setup_app_shortcuts()
        self._setup_label_shortcuts()
        self._build_status_bar()

        self._update_actions()
        self._refresh_status()

    # ---------------------------------------------------- mode resolution

    def _select_initial_mode(self) -> AnnotationMode:
        if not self.modes:
            QMessageBox.critical(
                self, "錯誤",
                f"找不到任何標註模式設定檔。\n請確認 {cfgmod.annotation_modes_dir()} 內含 *.json。",
            )
            sys.exit(1)
        wanted = self.prefs.active_mode_id
        for m in self.modes:
            if m.id == wanted:
                return m
        return self.modes[0]

    # --------------------------------------------------------------- ui build

    def _build_status_bar(self):
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.status_mode_label = QLabel()
        self.status.addPermanentWidget(self.status_mode_label)

    def _build_menu(self):
        mb = self.menuBar()

        # File
        m_file = mb.addMenu("檔案(&F)")
        self.act_open = QAction("開啟檔案…", self)
        self.act_open.setShortcut(self.prefs.app_shortcut("open", "Ctrl+O"))
        self.act_open.triggered.connect(self.action_open)
        m_file.addAction(self.act_open)

        self.act_save = QAction("儲存標註進度 (.lbtxt)", self)
        self.act_save.setShortcut(self.prefs.app_shortcut("save", "Ctrl+S"))
        self.act_save.triggered.connect(self.action_save)
        m_file.addAction(self.act_save)

        self.act_save_as = QAction("另存標註進度為…", self)
        self.act_save_as.triggered.connect(self.action_save_as)
        m_file.addAction(self.act_save_as)

        m_file.addSeparator()
        self.act_export = QAction("匯出模型用 .txt…", self)
        self.act_export.setShortcut(self.prefs.app_shortcut("export_txt", "Ctrl+E"))
        self.act_export.triggered.connect(self.action_export)
        m_file.addAction(self.act_export)

        m_file.addSeparator()
        self.act_quit = QAction("離開", self)
        self.act_quit.setShortcut("Ctrl+Q")
        self.act_quit.triggered.connect(self.close)
        m_file.addAction(self.act_quit)

        # Edit
        m_edit = mb.addMenu("編輯(&E)")
        self.act_remove_ann = QAction("刪除游標處標註", self)
        self.act_remove_ann.setShortcut(self.prefs.app_shortcut("remove_annotation", "Ctrl+D"))
        self.act_remove_ann.triggered.connect(self.action_remove_annotation_at_cursor)
        m_edit.addAction(self.act_remove_ann)

        m_edit.addSeparator()
        self.act_next_file = QAction("下一個檔案", self)
        self.act_next_file.setShortcut(self.prefs.app_shortcut("next_file", "Alt+Down"))
        self.act_next_file.triggered.connect(lambda: self.file_panel.select_relative(1))
        m_edit.addAction(self.act_next_file)

        self.act_prev_file = QAction("上一個檔案", self)
        self.act_prev_file.setShortcut(self.prefs.app_shortcut("prev_file", "Alt+Up"))
        self.act_prev_file.triggered.connect(lambda: self.file_panel.select_relative(-1))
        m_edit.addAction(self.act_prev_file)

        # Annotate
        self.menu_annotate = mb.addMenu("標註(&A)")
        self._populate_annotate_menu()

        # Mode
        m_mode = mb.addMenu("標註模式(&M)")
        self.mode_action_group = QActionGroup(self)
        self.mode_action_group.setExclusive(True)
        for m in self.modes:
            act = QAction(m.name, self, checkable=True)
            act.setData(m.id)
            if m.id == self.mode.id:
                act.setChecked(True)
            act.triggered.connect(self._on_mode_action)
            self.mode_action_group.addAction(act)
            m_mode.addAction(act)
        m_mode.addSeparator()
        act_open_modes_dir = QAction("開啟模式資料夾", self)
        act_open_modes_dir.triggered.connect(self._open_modes_dir)
        m_mode.addAction(act_open_modes_dir)

        # Help
        m_help = mb.addMenu("說明(&H)")
        act_about = QAction("關於 LexiArbiter", self)
        act_about.triggered.connect(self._show_about)
        m_help.addAction(act_about)

    def _populate_annotate_menu(self):
        self.menu_annotate.clear()
        for g in self.mode.groups:
            sub = self.menu_annotate.addMenu(g.name)
            for lb in g.labels:
                act = QAction(_swatch_icon(lb.color), lb.name, self)
                shortcut = self.prefs.label_shortcut(g.id, lb.id, lb.shortcut)
                if shortcut:
                    act.setShortcut(shortcut)
                act.triggered.connect(self._make_label_handler(g.id, lb.id))
                sub.addAction(act)
            sub.addSeparator()
            act_clear = QAction(f"清除「{g.name}」於選取段", self)
            act_clear.triggered.connect(self._make_clear_group_handler(g.id))
            sub.addAction(act_clear)

    def _build_toolbar(self):
        tb = QToolBar("標註工具列", self)
        tb.setIconSize(QSize(18, 18))
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        self.toolbar = tb

        a_open = tb.addAction(_swatch_icon("#FFFFFF"), "開啟檔案")
        a_open.triggered.connect(self.action_open)

        a_save = tb.addAction(_swatch_icon("#FFFFFF"), "儲存進度")
        a_save.triggered.connect(self.action_save)

        a_export = tb.addAction(_swatch_icon("#FFFFFF"), "匯出 .txt")
        a_export.triggered.connect(self.action_export)

        tb.addSeparator()
        self._populate_label_buttons()

    def _populate_label_buttons(self):
        # Remove any existing label-button widgets we added previously.
        if hasattr(self, "_label_button_actions"):
            for a in self._label_button_actions:
                self.toolbar.removeAction(a)
        self._label_button_actions = []

        for gi, g in enumerate(self.mode.groups):
            if gi > 0:
                self._label_button_actions.append(self.toolbar.addSeparator())
            grp_label = QLabel(f"  {g.name}：")
            self._label_button_actions.append(self.toolbar.addWidget(grp_label))
            for lb in g.labels:
                btn = QPushButton(lb.name)
                btn.setCursor(Qt.PointingHandCursor)
                shortcut = self.prefs.label_shortcut(g.id, lb.id, lb.shortcut)
                tip = lb.name
                if shortcut:
                    tip += f"  ({shortcut})"
                btn.setToolTip(tip)
                btn.setStyleSheet(self._button_style_for(lb))
                btn.clicked.connect(self._make_label_handler(g.id, lb.id))
                action = self.toolbar.addWidget(btn)
                self._label_button_actions.append(action)

    def _button_style_for(self, lb: LabelDef) -> str:
        if lb.color:
            return (
                f"QPushButton {{ background-color: {lb.color}; color: #1B1B1B; "
                f"border: 1px solid #333; border-radius: 6px; padding: 4px 12px; }}"
                f"QPushButton:hover {{ border: 1px solid #000; }}"
            )
        return (
            "QPushButton { background-color: #ECEFF1; color: #1B1B1B; "
            "border: 1px solid #90A4AE; border-radius: 6px; padding: 4px 12px; }"
            "QPushButton:hover { border: 1px solid #455A64; }"
        )

    # ----------------------------------------------------------- shortcuts

    def _setup_app_shortcuts(self):
        # menu actions already carry shortcuts; nothing additional here.
        pass

    def _setup_label_shortcuts(self):
        # Remove previous shortcut objects when switching mode.
        if hasattr(self, "_label_shortcuts"):
            for sc in self._label_shortcuts:
                sc.setParent(None)
        self._label_shortcuts: list[QShortcut] = []
        for g in self.mode.groups:
            for lb in g.labels:
                key = self.prefs.label_shortcut(g.id, lb.id, lb.shortcut)
                if not key:
                    continue
                sc = QShortcut(QKeySequence(key), self)
                sc.activated.connect(self._make_label_handler(g.id, lb.id))
                self._label_shortcuts.append(sc)

    # --------------------------------------------------------- annotate ops

    def _make_label_handler(self, group_id: str, label_id: str):
        def handler(*_):
            self.apply_label(group_id, label_id)
        return handler

    def _make_clear_group_handler(self, group_id: str):
        def handler(*_):
            self.clear_group_in_selection(group_id)
        return handler

    def apply_label(self, group_id: str, label_id: str):
        if self.doc is None:
            self.status.showMessage("請先開啟一個檔案再進行標註。", 4000)
            return
        if not self.editor.has_selection():
            ann_id = self.editor.annotation_at_cursor()
            if ann_id is None:
                self.status.showMessage("請先選取一段文字，或將游標放在已標註的範圍內。", 4000)
                return
            ann = self.doc.find_annotation(ann_id)
            if ann is None:
                return
            ann.labels[group_id] = label_id
            self.doc.dirty = True
            self.editor.refresh_highlights()
            self._refresh_status()
            return

        s, e = self.editor.storage_selection()
        # If selection coincides exactly with an existing annotation, update it.
        existing = [a for a in self.doc.annotations
                    if a.start == s and a.end == e]
        if existing:
            ann = existing[0]
            ann.labels[group_id] = label_id
        else:
            # If selection overlaps existing annotations *partially*, ask user.
            overlapping = self.doc.annotations_in_range(s, e)
            if overlapping:
                reply = QMessageBox.question(
                    self, "重疊處理",
                    "選取範圍與既有標註重疊。\n要刪除既有標註再新增嗎？\n（按否將與既有標註並存。）",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                )
                if reply == QMessageBox.Cancel:
                    return
                if reply == QMessageBox.Yes:
                    for a in overlapping:
                        self.doc.remove_annotation(a.id)
            ann = Annotation(start=s, end=e, labels={group_id: label_id})
            self.doc.add_annotation(ann)
        self.doc.dirty = True
        self.editor.refresh_highlights()
        self._refresh_status()

    def clear_group_in_selection(self, group_id: str):
        if self.doc is None:
            return
        s, e = self.editor.storage_selection()
        if e <= s:
            ann_id = self.editor.annotation_at_cursor()
            if ann_id is None:
                return
            ann = self.doc.find_annotation(ann_id)
            if ann is None:
                return
            ann.labels.pop(group_id, None)
            if not ann.labels:
                self.doc.remove_annotation(ann.id)
        else:
            for a in list(self.doc.annotations_in_range(s, e)):
                a.labels.pop(group_id, None)
                if not a.labels:
                    self.doc.remove_annotation(a.id)
        self.doc.dirty = True
        self.editor.refresh_highlights()
        self._refresh_status()

    def action_remove_annotation_at_cursor(self):
        if self.doc is None:
            return
        # Prefer selection scope if set.
        s, e = self.editor.storage_selection()
        if e > s:
            for a in list(self.doc.annotations_in_range(s, e)):
                self.doc.remove_annotation(a.id)
            self.editor.refresh_highlights()
            self._refresh_status()
            return
        ann_id = self.editor.annotation_at_cursor()
        if ann_id is None:
            self.status.showMessage("游標處沒有標註可刪除。", 3000)
            return
        if self.doc.remove_annotation(ann_id):
            self.editor.refresh_highlights()
            self._refresh_status()

    # ----------------------------------------------------------- file ops

    def _confirm_unsaved(self) -> bool:
        if self.doc is None or not self.doc.dirty:
            return True
        if not self.prefs.behavior.get("confirm_unsaved_on_switch", True):
            return True
        reply = QMessageBox.question(
            self, "未儲存",
            "目前的標註尚未儲存，是否要儲存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Save:
            return self.action_save()
        if reply == QMessageBox.Discard:
            return True
        return False

    def action_open(self):
        if not self._confirm_unsaved():
            return
        start_dir = ""
        if self.doc and self.doc.file_path:
            start_dir = str(Path(self.doc.file_path).parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "開啟檔案", start_dir,
            "支援的格式 (*.json *.lbtxt);;判決 JSON (*.json);;標註進度 (*.lbtxt);;所有檔案 (*.*)"
        )
        if path:
            self.load_file(path)

    def _handle_file_open_requested(self, path: str):
        if self.doc and self.doc.file_path and Path(path).resolve() == Path(self.doc.file_path).resolve():
            return
        if not self._confirm_unsaved():
            return
        self.load_file(path)

    def load_file(self, path: str):
        try:
            doc = iomod.load_any(path)
        except Exception as e:
            QMessageBox.critical(self, "讀檔失敗", str(e))
            return

        # If the doc was saved under a different schema, warn.
        if doc.schema_id and doc.schema_id != self.mode.id:
            target = next((m for m in self.modes if m.id == doc.schema_id), None)
            if target is not None:
                reply = QMessageBox.question(
                    self, "切換標註模式？",
                    f"此檔案是以「{target.name}」模式標註的，是否切換到該模式以正確顯示？",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self._switch_mode(target.id, persist=False)

        self.doc = doc
        self.editor.attach(doc, self.mode, self.prefs)
        self._update_window_title()
        # Update file panel to the directory of this doc.
        self.file_panel.set_directory(Path(path).parent, Path(path))
        self._update_actions()
        self._refresh_status()

    def action_save(self) -> bool:
        if self.doc is None:
            return False
        path = self.doc.file_path
        if path and path.lower().endswith(".lbtxt"):
            try:
                iomod.save_lbtxt(self.doc, path, self.mode)
            except Exception as e:
                QMessageBox.critical(self, "儲存失敗", str(e))
                return False
            self.status.showMessage(f"已儲存：{path}", 4000)
            self.file_panel.refresh()
            self._update_window_title()
            return True
        return self.action_save_as()

    def action_save_as(self) -> bool:
        if self.doc is None:
            return False
        if self.doc.file_path:
            base = Path(self.doc.file_path)
            default = str(base.with_suffix(".lbtxt"))
        else:
            default = "annotation.lbtxt"
        path, _ = QFileDialog.getSaveFileName(
            self, "另存標註進度", default,
            "LexiArbiter 進度 (*.lbtxt)"
        )
        if not path:
            return False
        if not path.lower().endswith(".lbtxt"):
            path = path + ".lbtxt"
        try:
            iomod.save_lbtxt(self.doc, path, self.mode)
        except Exception as e:
            QMessageBox.critical(self, "儲存失敗", str(e))
            return False
        self.status.showMessage(f"已儲存：{path}", 4000)
        self.file_panel.set_directory(Path(path).parent, Path(path))
        self._update_window_title()
        return True

    def action_export(self):
        if self.doc is None:
            return
        if not self.doc.annotations:
            QMessageBox.information(self, "提示", "目前沒有任何標註可以匯出。")
            return
        if self.doc.file_path:
            base = Path(self.doc.file_path)
            default = str(base.with_suffix(".txt"))
        else:
            default = "export.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "匯出模型用 .txt", default,
            "純文字 (*.txt)"
        )
        if not path:
            return
        if not path.lower().endswith(".txt"):
            path = path + ".txt"
        try:
            summary = iomod.export_txt(self.doc, path, self.mode)
        except Exception as e:
            QMessageBox.critical(self, "匯出失敗", str(e))
            return

        msg = (
            f"成功匯出 {summary['written']} 段。\n"
            f"未涵蓋字元：{summary['unannotated_chars']}\n"
            f"群組未填齊段落：{summary['partial_count']}"
        )
        if summary["warnings"]:
            msg += "\n\n警告：\n" + "\n".join(summary["warnings"][:8])
            if len(summary["warnings"]) > 8:
                msg += f"\n（其餘 {len(summary['warnings']) - 8} 條已略過）"

        if (summary["partial_count"] > 0
                and self.prefs.behavior.get("warn_partial_groups_on_export", True)):
            QMessageBox.warning(self, "匯出完成（含警告）", msg)
        else:
            QMessageBox.information(self, "匯出完成", msg)
        self.file_panel.refresh()

    # -------------------------------------------------------- mode switching

    def _on_mode_action(self):
        act = self.mode_action_group.checkedAction()
        if act is None:
            return
        mode_id = act.data()
        self._switch_mode(mode_id, persist=True)

    def _switch_mode(self, mode_id: str, persist: bool):
        target = next((m for m in self.modes if m.id == mode_id), None)
        if target is None:
            return
        if self.doc is not None and self.doc.dirty:
            reply = QMessageBox.question(
                self, "切換模式",
                "切換標註模式可能讓既有標籤對應不到。建議先存檔。是否仍要切換？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                # revert the menu check
                for a in self.mode_action_group.actions():
                    a.setChecked(a.data() == self.mode.id)
                return
        self.mode = target
        if persist:
            self.prefs.active_mode_id = target.id
            try:
                self.prefs.save()
            except Exception:
                pass
        self._populate_annotate_menu()
        self._populate_label_buttons()
        self._setup_label_shortcuts()
        if self.doc is not None:
            self.editor.attach(self.doc, self.mode, self.prefs)
        self._refresh_status()
        self._update_window_title()

    def _open_modes_dir(self):
        d = cfgmod.annotation_modes_dir()
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(d)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f"open '{d}'")
        else:
            os.system(f"xdg-open '{d}'")

    # ------------------------------------------------------------ misc UI

    def _build_context_menu(self, menu: QMenu, ann_id: Optional[str],
                            sel_start: int, sel_end: int):
        if self.doc is None:
            return
        has_selection = sel_end > sel_start

        # If hovering over an annotation, show its info.
        if ann_id is not None:
            ann = self.doc.find_annotation(ann_id)
            if ann is not None:
                lbl_lines = []
                for g in self.mode.groups:
                    lid = ann.labels.get(g.id)
                    if lid:
                        lb = g.label(lid)
                        if lb:
                            lbl_lines.append(f"{g.name}：{lb.name}")
                head = QAction("　|　".join(lbl_lines) if lbl_lines else "(無標籤)", self)
                head.setEnabled(False)
                menu.addAction(head)
                menu.addSeparator()

        for g in self.mode.groups:
            sub = menu.addMenu(g.name)
            for lb in g.labels:
                act = QAction(_swatch_icon(lb.color), lb.name, self)
                shortcut = self.prefs.label_shortcut(g.id, lb.id, lb.shortcut)
                if shortcut:
                    act.setShortcut(shortcut)
                act.triggered.connect(self._make_label_handler(g.id, lb.id))
                sub.addAction(act)
            sub.addSeparator()
            act_clear = QAction(f"清除「{g.name}」", self)
            act_clear.triggered.connect(self._make_clear_group_handler(g.id))
            sub.addAction(act_clear)

        menu.addSeparator()
        act_remove = QAction("刪除此處標註", self)
        act_remove.triggered.connect(self.action_remove_annotation_at_cursor)
        if not has_selection and ann_id is None:
            act_remove.setEnabled(False)
        menu.addAction(act_remove)

    def _on_selection_changed(self, s: int, e: int):
        if e > s and self.doc is not None:
            seg = self.doc.text[s:e]
            preview = seg.replace("\r", " ").replace("\n", " ")
            if len(preview) > 60:
                preview = preview[:57] + "…"
            self.status.showMessage(f"選取 {e - s} 字：{preview}", 0)
        else:
            self._refresh_status()

    def _refresh_status(self):
        mode_text = f"模式：{self.mode.name}（{self.mode.id}）"
        self.status_mode_label.setText(mode_text)
        if self.doc is None:
            self.status.showMessage("尚未開啟檔案。可從右側清單或檔案 → 開啟。", 0)
        else:
            n = len(self.doc.annotations)
            grp_total = sum(len(a.labels) for a in self.doc.annotations)
            self.status.showMessage(
                f"已標註段落：{n}　|　標籤總數：{grp_total}　|　文字長度：{len(self.doc.text)}",
                0,
            )

    def _update_window_title(self):
        title = f"{__app_name__} - 法律文件標註工具"
        if self.doc is not None:
            name = self.doc.source_filename or (Path(self.doc.file_path).name if self.doc.file_path else "未命名")
            mark = "*" if self.doc.dirty else ""
            title = f"{name}{mark} - {title}"
        self.setWindowTitle(title)

    def _update_actions(self):
        has_doc = self.doc is not None
        for a in (self.act_save, self.act_save_as, self.act_export, self.act_remove_ann):
            a.setEnabled(has_doc)

    # ------------------------------------------------------------ events

    def closeEvent(self, ev):
        if not self._confirm_unsaved():
            ev.ignore()
            return
        super().closeEvent(ev)

    # ------------------------------------------------------------ misc

    def _show_about(self):
        QMessageBox.about(
            self,
            f"關於 {__app_name__}",
            (
                f"<h3>{__app_name__} {__version__}</h3>"
                "<p>面向法律判決 multi-task learning 標註的桌面工具。</p>"
                "<p>支援 .json / .lbtxt 開啟、.lbtxt 進度存檔、.txt 模型用匯出，"
                "並可透過 <code>configs/annotation_modes/*.json</code> 切換標註模式。</p>"
            ),
        )
