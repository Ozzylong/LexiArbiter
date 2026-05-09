"""The annotation editor widget.

We keep the *original* text in `Document.text` (with raw ``\\r\\n`` line
endings, exactly as it appears in the source JSON), because that is what gets
serialised into ``.lbtxt`` / ``.txt`` output and what the user's MTL pipeline
preprocesses later.

For *display*, ``\\r\\n`` is normalised to ``\\n`` so Qt renders nicely. We
maintain two-way maps between the two coordinate systems so annotation offsets
always refer to the original (storage) text.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import (
    QAction, QColor, QKeySequence, QShortcut, QTextCharFormat, QTextCursor,
    QFont, QPalette,
)
from PySide6.QtWidgets import QMenu, QTextEdit

from ..core.config import AnnotationMode, UserPreferences
from ..core.models import Annotation, Document


class _OffsetMap:
    """Bidirectional map between storage offsets (with \\r\\n) and display
    offsets (with \\n)."""

    def __init__(self, raw: str):
        # Walk through `raw` and build a mapping.
        self.storage_to_display: list[int] = [0] * (len(raw) + 1)
        self.display_to_storage: list[int] = []
        d = 0
        i = 0
        while i < len(raw):
            self.storage_to_display[i] = d
            ch = raw[i]
            if ch == "\r" and i + 1 < len(raw) and raw[i + 1] == "\n":
                # Skip the \r entirely in display.
                self.storage_to_display[i + 1] = d  # \n still maps to current d
                self.display_to_storage.append(i + 1)  # display position d -> storage \n
                d += 1
                i += 2
            else:
                self.display_to_storage.append(i)
                d += 1
                i += 1
        self.storage_to_display[len(raw)] = d
        self.display_to_storage.append(len(raw))

    def to_display(self, storage_offset: int) -> int:
        if storage_offset <= 0:
            return 0
        if storage_offset >= len(self.storage_to_display):
            return self.storage_to_display[-1]
        return self.storage_to_display[storage_offset]

    def to_storage(self, display_offset: int) -> int:
        if display_offset <= 0:
            return 0
        if display_offset >= len(self.display_to_storage):
            return self.display_to_storage[-1]
        return self.display_to_storage[display_offset]


def _hex_to_qcolor(value: Optional[str], alpha: int = 110) -> Optional[QColor]:
    if not value:
        return None
    c = QColor(value)
    if not c.isValid():
        return None
    c.setAlpha(alpha)
    return c


class AnnotationEditor(QTextEdit):
    """Read-only-ish text view that renders annotations as background highlights.

    Selection is editable in the sense that the user can click and drag to
    select text spans, and we expose those spans for the host window to apply
    annotations to. The text content itself cannot be modified.
    """

    annotation_clicked = Signal(str)  # annotation id
    selection_changed = Signal(int, int)  # storage start, storage end

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        # Allow text selection but keep cursor visible.
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.selectionChanged.connect(self._on_selection_changed)

        self._doc: Optional[Document] = None
        self._mode: Optional[AnnotationMode] = None
        self._prefs: Optional[UserPreferences] = None
        self._omap: Optional[_OffsetMap] = None
        self._context_menu_builder = None

    # ------------------------------------------------------------------ setup

    def attach(self, doc: Document, mode: AnnotationMode, prefs: UserPreferences):
        self._doc = doc
        self._mode = mode
        self._prefs = prefs

        font = QFont(prefs.ui.get("font_family", "Microsoft JhengHei UI"),
                     prefs.ui.get("font_size", 14))
        self.setFont(font)

        # Normalise \r\n -> \n for display.
        display_text = doc.text.replace("\r\n", "\n")
        self._omap = _OffsetMap(doc.text)
        self.setPlainText(display_text)

        # Block-format with line spacing.
        self._apply_line_spacing(prefs.ui.get("line_spacing", 1.4))
        self.refresh_highlights()

    def _apply_line_spacing(self, factor: float):
        if not self._doc:
            return
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.Document)
        block_fmt = cursor.blockFormat()
        block_fmt.setLineHeight(int(factor * 100), 1)  # ProportionalHeight
        cursor.setBlockFormat(block_fmt)

    def set_context_menu_builder(self, fn):
        """`fn(menu, ann_id_or_None, sel_start, sel_end)` populates the menu."""
        self._context_menu_builder = fn

    # ----------------------------------------------------------- selection

    def storage_selection(self) -> tuple[int, int]:
        if self._omap is None:
            return (0, 0)
        cur = self.textCursor()
        d_start = cur.selectionStart()
        d_end = cur.selectionEnd()
        return (self._omap.to_storage(d_start), self._omap.to_storage(d_end))

    def has_selection(self) -> bool:
        s, e = self.storage_selection()
        return e > s

    def _on_selection_changed(self):
        s, e = self.storage_selection()
        self.selection_changed.emit(s, e)

    # ------------------------------------------------------ highlight render

    def refresh_highlights(self):
        if self._doc is None or self._mode is None or self._omap is None:
            return
        selections = []
        for ann in self._doc.annotations:
            sel = QTextEdit.ExtraSelection()
            cursor = self.textCursor()
            d_start = self._omap.to_display(ann.start)
            d_end = self._omap.to_display(ann.end)
            cursor.setPosition(d_start)
            cursor.setPosition(d_end, QTextCursor.KeepAnchor)
            sel.cursor = cursor

            fmt = QTextCharFormat()
            self._apply_format_for_labels(fmt, ann)
            sel.format = fmt
            selections.append(sel)
        self.setExtraSelections(selections)

    def _apply_format_for_labels(self, fmt: QTextCharFormat, ann: Annotation):
        """First group with a non-null color drives the background.
        Other group labels are reflected via underline style."""
        if self._mode is None:
            return
        bg_color: Optional[QColor] = None
        primary_label_name = ""
        underline_style = QTextCharFormat.NoUnderline
        underline_color: Optional[QColor] = None
        tooltip_parts: list[str] = []

        for g in self._mode.groups:
            lid = ann.labels.get(g.id)
            if not lid:
                continue
            lb = g.label(lid)
            if lb is None:
                continue
            tooltip_parts.append(f"{g.name}：{lb.name}")
            color = _hex_to_qcolor(lb.color, alpha=110)
            if color is not None and bg_color is None:
                bg_color = color
                primary_label_name = lb.name
            elif color is None:
                # Auxiliary: pick underline style by index in group's labels.
                idx = g.labels.index(lb)
                styles = [
                    QTextCharFormat.SingleUnderline,
                    QTextCharFormat.DashUnderline,
                    QTextCharFormat.DotLine,
                    QTextCharFormat.WaveUnderline,
                ]
                underline_style = styles[idx % len(styles)]
                # Use a darkened version of bg if available, else a neutral grey.
                if bg_color is not None:
                    deep = QColor(bg_color)
                    deep.setAlpha(255)
                    underline_color = deep.darker(160)
                else:
                    underline_color = QColor("#455A64")

        if bg_color is None:
            # No primary color -> light yellow fallback so user still sees it.
            bg_color = _hex_to_qcolor("#FFF59D", alpha=110)

        fmt.setBackground(bg_color)
        if underline_style != QTextCharFormat.NoUnderline:
            fmt.setUnderlineStyle(underline_style)
            if underline_color is not None:
                fmt.setUnderlineColor(underline_color)
        if tooltip_parts:
            fmt.setToolTip("　|　".join(tooltip_parts))

    # ----------------------------------------------------------- context menu

    def _on_context_menu(self, pos: QPoint):
        if self._context_menu_builder is None:
            return
        menu = QMenu(self)
        cursor = self.cursorForPosition(pos)
        d_pos = cursor.position()
        if self._omap is None:
            return
        storage_pos = self._omap.to_storage(d_pos)
        sel_start, sel_end = self.storage_selection()
        ann_id = None
        if self._doc is not None:
            anns_at = self._doc.annotations_at(storage_pos)
            if anns_at:
                ann_id = anns_at[-1].id
        self._context_menu_builder(menu, ann_id, sel_start, sel_end)
        if not menu.isEmpty():
            menu.exec(self.mapToGlobal(pos))

    def annotation_at_cursor(self) -> Optional[str]:
        if self._doc is None or self._omap is None:
            return None
        cur = self.textCursor()
        storage_pos = self._omap.to_storage(cur.position())
        anns_at = self._doc.annotations_at(storage_pos)
        return anns_at[-1].id if anns_at else None

    def jump_to_annotation(self, ann_id: str):
        if self._doc is None or self._omap is None:
            return
        ann = self._doc.find_annotation(ann_id)
        if ann is None:
            return
        cur = self.textCursor()
        cur.setPosition(self._omap.to_display(ann.start))
        cur.setPosition(self._omap.to_display(ann.end), QTextCursor.KeepAnchor)
        self.setTextCursor(cur)
        self.ensureCursorVisible()
