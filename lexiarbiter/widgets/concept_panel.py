"""Concept management UI components."""
import uuid
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QLineEdit, QPushButton, 
    QLabel, QWidget, QMessageBox
)

class TermConceptDialog(QDialog):
    """彈出視窗：設定術語的綁定概念與上位概念，並做最終確認。"""
    
    def __init__(self, concepts: dict[str, str], term_text: str, explanation_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("設定概念與標註確認")
        self.resize(600, 420)
        
        # 放大預設字體
        font = self.font()
        font.setPointSize(font.pointSize() + 1)
        self.setFont(font)
        
        # 追蹤是否要「回上一步」
        self.wants_back = False
        
        layout = QVBoxLayout(self)
        
        from PySide6.QtWidgets import QPlainTextEdit
        
        # [唯讀資訊區]
        layout.addWidget(QLabel("<b>📌 您選取的術語：</b>"))
        txt_term = QPlainTextEdit(term_text)
        txt_term.setReadOnly(True)
        txt_term.setMaximumHeight(60)
        layout.addWidget(txt_term)
        
        layout.addWidget(QLabel("<b>📖 您選取的解釋：</b>"))
        txt_exp = QPlainTextEdit(explanation_text)
        txt_exp.setReadOnly(True)
        txt_exp.setMaximumHeight(100)
        layout.addWidget(txt_exp)
        
        layout.addSpacing(10)
        
        # [概念設定區]
        from PySide6.QtWidgets import QComboBox
        # 為了排序建立 list
        sorted_concepts = sorted(concepts.items(), key=lambda x: x[1])
        
        layout.addWidget(QLabel("<b>1. 綁定概念 (Bound Concept)：</b>"))
        self.bound_combo = QComboBox()
        self.bound_combo.setEditable(True)
        self.bound_combo.addItem(" (無) ", None)
        for cid, name in sorted_concepts:
            self.bound_combo.addItem(name, cid)
        self.bound_combo.setCurrentText(term_text) # 預設帶入術語文字
        layout.addWidget(self.bound_combo)
        
        layout.addSpacing(10)
        
        layout.addWidget(QLabel("<b>2. 上位概念 (Broader Concept)：</b>"))
        self.broader_combo = QComboBox()
        self.broader_combo.setEditable(True)
        self.broader_combo.addItem(" (無) ", None)
        for cid, name in sorted_concepts:
            self.broader_combo.addItem(name, cid)
        layout.addWidget(self.broader_combo)
        
        layout.addStretch()
        
        # [按鈕區]
        btn_layout = QHBoxLayout()
        self.btn_ok = QPushButton("確定並儲存")
        self.btn_ok.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 6px; border-radius: 4px;")
        self.btn_ok.clicked.connect(self.accept)
        
        self.btn_back = QPushButton("回上一步 (重選解釋)")
        self.btn_back.setStyleSheet("background-color: #FF9800; color: white; padding: 6px; border-radius: 4px;")
        self.btn_back.clicked.connect(self._on_back_clicked)
        
        self.btn_cancel = QPushButton("取消 (放棄標註)")
        self.btn_cancel.setStyleSheet("background-color: #546E7A; color: white; padding: 6px; border-radius: 4px;")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_back)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def _on_back_clicked(self):
        self.wants_back = True
        self.reject()

    def _extract_combo_data(self, combo) -> tuple[str | None, str | None]:
        text = combo.currentText().strip()
        if not text or text == "(無)":
            return None, None
        
        # 檢查是否在既有清單中
        idx = combo.findText(text)
        if idx >= 0:
            # 找到現有的，回傳它的 ID
            cid = combo.itemData(idx)
            if cid is not None:
                return cid, None
        # 使用者手打的新概念
        return None, text

    def get_results(self) -> tuple[str | None, str | None, str | None, str | None, bool]:
        """回傳 (bound_id, bound_new_name, broader_id, broader_new_name, wants_back)"""
        if self.wants_back:
            return None, None, None, None, True
            
        b_id, b_name = self._extract_combo_data(self.bound_combo)
        br_id, br_name = self._extract_combo_data(self.broader_combo)
        
        return b_id, b_name, br_id, br_name, False


class ConceptSidebar(QWidget):
    """側邊欄：顯示當前文件所有的概念池"""
    concept_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        title = QLabel("文件概念清單 (Concepts)")
        f = title.font()
        f.setBold(True)
        title.setFont(f)
        
        self.list_widget = QListWidget()
        
        layout.addWidget(title)
        layout.addWidget(self.list_widget)

    def refresh(self, doc):
        self.list_widget.clear()
        if not doc or not hasattr(doc, 'concepts'):
            return
        for cid, name in doc.concepts.items():
            self.list_widget.addItem(f"● {name}")

        # 讓側邊欄的概念清單也依照筆畫/字母自動排序
        self.list_widget.sortItems(Qt.AscendingOrder)