"""Right-hand file list panel.

Shows every ``.json`` / ``.lexa`` / ``.txt`` file in the same folder as the
currently-loaded document. A small icon next to each file shows its annotation
state:

* ``●`` (filled) - the working file (currently open)
* ``◐`` - has an associated ``.lexa`` (work-in-progress) on disk
* ``◇`` - has an associated ``.txt`` (final export) but no ``.lexa``
* ``○`` - raw, untouched

The current row also displays a trailing ``*`` while the in-memory document
has unsaved changes, mirroring the dirty marker in the window title.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)


_EXTS = (".json", ".lexa", ".txt")


def _stem_no_lexa(p: Path) -> str:
    """Stem used to group raw json/lexa/txt of the same judgment."""
    return p.stem


class FilePanel(QWidget):
    file_open_requested = Signal(str)  # absolute path

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.title = QLabel("同資料夾檔案")
        font = self.title.font()
        font.setPointSize(font.pointSize() + 1)
        font.setBold(True)
        self.title.setFont(font)

        self.list = QListWidget()
        self.list.itemActivated.connect(self._on_item_activated)
        self.list.itemDoubleClicked.connect(self._on_item_activated)

        layout.addWidget(self.title)
        layout.addWidget(self.list, 1)

        self._dir: Optional[Path] = None
        self._current_path: Optional[Path] = None
        self._current_dirty: bool = False

    # ----------------------------------------------------------- public api

    def set_directory(self, directory: Optional[Path], current_path: Optional[Path]):
        self._dir = Path(directory) if directory else None
        self._current_path = Path(current_path) if current_path else None
        # 切檔後 dirty 由 MainWindow._update_window_title() 在後續同步補正。
        self._current_dirty = False
        self.refresh()

    def set_dirty(self, dirty: bool):
        """更新「目前列」未存檔標記，不觸發目錄重讀。"""
        if dirty == self._current_dirty:
            return
        self._current_dirty = dirty
        if self._current_path is None:
            return
        try:
            current_resolved = self._current_path.resolve()
        except OSError:
            return
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item is None:
                continue
            path_str = item.data(Qt.UserRole)
            if not path_str:
                continue
            try:
                if Path(path_str).resolve() != current_resolved:
                    continue
            except OSError:
                continue
            text = item.text()
            if dirty:
                if not text.endswith("*"):
                    item.setText(text + "*")
            else:
                if text.endswith("*"):
                    item.setText(text[:-1])
            break

    def refresh(self):
        self.list.clear()
        if not self._dir or not self._dir.exists():
            return

        # Group sibling files by stem so we can show one row per judgment.
        files: dict[str, dict[str, Path]] = {}
        try:
            entries = sorted(self._dir.iterdir())
        except OSError:
            log.warning("無法讀取目錄：%s", self._dir, exc_info=True)
            return
        for entry in entries:
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if ext not in _EXTS:
                continue
            files.setdefault(entry.stem, {})[ext] = entry

        for stem in sorted(files.keys()):
            group = files[stem]
            # Decide which to display + what state badge to show.
            primary = group.get(".lexa") or group.get(".json") or group.get(".txt")
            if primary is None:
                continue

            has_lexa = ".lexa" in group
            has_txt = ".txt" in group
            is_current = (
                self._current_path is not None
                and primary.resolve() == self._current_path.resolve()
            )

            if is_current:
                badge = "●"
            elif has_lexa:
                badge = "◐"
            elif has_txt:
                badge = "◇"
            else:
                badge = "○"

            dirty_mark = "*" if (is_current and self._current_dirty) else ""
            item = QListWidgetItem(f"{badge}  {primary.name}{dirty_mark}")
            item.setData(Qt.UserRole, str(primary))
            tip = f"{primary.name}"
            if has_lexa:
                tip += "\n• 已存在 .lexa 標註進度"
            if has_txt:
                tip += "\n• 已存在 .txt 匯出檔"
            item.setToolTip(tip)
            if is_current:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.list.addItem(item)

    def select_path(self, path: Optional[Path]):
        self._current_path = Path(path) if path else None
        self.refresh()

    def select_relative(self, delta: int):
        if self.list.count() == 0:
            return
        cur = self.list.currentRow()
        if cur < 0:
            cur = 0
        new = max(0, min(self.list.count() - 1, cur + delta))
        self.list.setCurrentRow(new)
        item = self.list.item(new)
        if item is not None:
            self.file_open_requested.emit(item.data(Qt.UserRole))

    # ------------------------------------------------------------ handlers

    def _on_item_activated(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if path:
            self.file_open_requested.emit(path)
