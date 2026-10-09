import uuid
from typing import Optional
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QMenu, QWidget, QVBoxLayout, QLabel
from PySide6.QtGui import QColor, QAction

from .base_handler import BaseModeHandler
from ..core.models import Annotation
from ..widgets.concept_panel import TermConceptDialog

class TermDefinitionHandler(BaseModeHandler):

    def handle_apply_label(self, group_id: str, label_id: str) -> bool:
        if not self.app.editor.has_selection():
            self.app.status.showMessage("請先選取一段文字作為術語。", 4000)
            return True
        s, e = self.app.editor.storage_selection()
        if not self.app._resolve_same_group_overlap(s, e, group_id):
            return True
            
        self.app._pending_term_info = (s, e, group_id, label_id)
        
        # 暫時高亮術語
        self.app.editor.highlight_pending_term(s, e, "#90A4AE")
        
        self.app._show_hud()
        self.app.status.showMessage("步驟 2/3：請在文章中反白選取該術語的『解釋段落』 (按 Esc 取消)", 0)
        
        cursor = self.app.editor.textCursor()
        cursor.clearSelection()
        self.app.editor.setTextCursor(cursor)
        return True

    def handle_selection_finished(self, global_pos: QPoint) -> bool:
        s_exp, e_exp = self.app.editor.storage_selection()
        
        # Bug 4 Fix: If selection exactly matches an annotation, show info card instead of quick menu
        if e_exp > s_exp and not getattr(self.app, "_pending_term_info", None):
            exact_matches = [a for a in self.app.doc.annotations if a.start == s_exp and a.end == e_exp]
            if exact_matches:
                self.on_annotation_clicked(exact_matches[-1].id)
                cursor = self.app.editor.textCursor()
                cursor.clearSelection()
                self.app.editor.setTextCursor(cursor)
                return True

        if not getattr(self.app, "_pending_term_info", None):
            return False

        if not (e_exp > s_exp):
            return True # Still handled, just ignored
            
        pending = self.app._pending_term_info
        
        # New selection workflow (length = 4)
        if len(pending) == 4 and pending[0] != "reselect":
            s_term, e_term, group_id, label_id = pending
            
            term_text = self.app.doc.text[s_term:e_term]
            exp_text = self.app.doc.text[s_exp:e_exp]
            
            self.app._hide_hud()
            
            dlg = TermConceptDialog(self.app.doc.concepts, term_text, exp_text, parent=self.app, is_edit_mode=True)
            
            while True:
                if dlg.exec():
                    b_id, b_name, br_id, br_name, wants_back = dlg.get_results()
                    if wants_back:
                        self.app._show_hud()
                        cursor = self.app.editor.textCursor()
                        cursor.clearSelection()
                        self.app.editor.setTextCursor(cursor)
                        break
                    
                    concept_id = None
                    if b_name:
                        existing_id = next((cid for cid, name in self.app.doc.concepts.items() if name == b_name), None)
                        if existing_id:
                            concept_id = existing_id
                        else:
                            import uuid
                            concept_id = "C_" + uuid.uuid4().hex[:8]
                            self.app.doc.concepts[concept_id] = b_name
                    elif b_id:
                        concept_id = b_id
                        
                    broader_id = None
                    if br_name:
                        existing_id = next((cid for cid, name in self.app.doc.concepts.items() if name == br_name), None)
                        if existing_id:
                            broader_id = existing_id
                        else:
                            import uuid
                            broader_id = "C_" + uuid.uuid4().hex[:8]
                            self.app.doc.concepts[broader_id] = br_name
                    elif br_id:
                        broader_id = br_id
                        
                    self.app.concept_panel.refresh(self.app.doc)
                    
                    ann = Annotation(
                        start=s_term, end=e_term, 
                        labels={group_id: label_id}, 
                        concept_id=concept_id,
                        explanation_start=s_exp,
                        explanation_end=e_exp,
                        broader_concept_id=broader_id
                    )
                    self.app.doc.add_annotation(ann)
                    self.app.doc.dirty = True
                    self.app.editor.clear_pending_term_highlight()
                    self.app.editor.clear_explanation_highlight()
                    self.app._pending_term_info = None
                    self.app.editor.refresh_highlights()
                    self.app._refresh_status()
                    self.app._update_window_title()
                    
                    cursor = self.app.editor.textCursor()
                    cursor.clearSelection()
                    self.app.editor.setTextCursor(cursor)
                    break
                else:
                    b_id, b_name, br_id, br_name, wants_back = dlg.get_results()
                    if wants_back:
                        self.app._show_hud()
                        cursor = self.app.editor.textCursor()
                        cursor.clearSelection()
                        self.app.editor.setTextCursor(cursor)
                        break
                    else:
                        self.app.editor.clear_pending_term_highlight()
                        self.app.editor.clear_explanation_highlight()
                        self.app._pending_term_info = None
                        cursor = self.app.editor.textCursor()
                        cursor.clearSelection()
                        self.app.editor.setTextCursor(cursor)
                        break
            return True
            
        elif len(pending) == 2 and pending[0] == "reselect":
            # Bug 3 Fix: Auto-save on reselect explanation
            ann_id = pending[1]
            ann = self.app.doc.find_annotation(ann_id)
            if ann:
                ann.explanation_start = s_exp
                ann.explanation_end = e_exp
                self.app.doc.dirty = True
                
            self.app._hide_hud()
            self.app.editor.clear_pending_term_highlight()
            self.app.editor.clear_explanation_highlight()
            self.app._pending_term_info = None
            self.app.editor.refresh_highlights()
            
            cursor = self.app.editor.textCursor()
            cursor.clearSelection()
            self.app.editor.setTextCursor(cursor)
            
            self.app.status.showMessage("已更新解釋段落。", 3000)
            return True
            
        return True

    def on_annotation_clicked(self, ann_id: str) -> bool:
        if getattr(self.app, "_pending_term_info", None):
            return False
        if not self.app.doc:
            return False
        ann = self.app.doc.find_annotation(ann_id)
        if not ann:
            return False
            
        if getattr(ann, "explanation_start", None) is not None and getattr(ann, "explanation_end", None) is not None:
            color = self.app.prefs.ui.get("explanation_highlight_color", "#90CAF9")
            self.app.editor.highlight_explanation(ann.explanation_start, ann.explanation_end, color)
            
        popup = QWidget(self.app, Qt.Popup)
        popup.setObjectName("TermPopup")
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(8, 8, 8, 8)
        
        c_bound = self.app.doc.concepts.get(ann.concept_id, "(無)") if getattr(ann, "concept_id", None) else "(無)"
        c_broader = self.app.doc.concepts.get(ann.broader_concept_id, "(無)") if getattr(ann, "broader_concept_id", None) else "(無)"
        
        exp_text = "(無)"
        if getattr(ann, "explanation_start", None) is not None and getattr(ann, "explanation_end", None) is not None:
            raw_text = self.app.doc.text[ann.explanation_start:ann.explanation_end].replace("\r", " ").replace("\n", " ")
            if len(raw_text) > 50:
                exp_text = raw_text[:47] + "..."
            else:
                exp_text = raw_text
                
        status_msg = f"概念: {c_bound}  |  上位: {c_broader}  |  解釋: {exp_text}"
        self.app.status.showMessage(status_msg, 0)
        
        layout.addWidget(QLabel(f"<b>綁定概念：</b> {c_bound}"))
        layout.addWidget(QLabel(f"<b>上位概念：</b> {c_broader}"))
        
        popup.setStyleSheet("""
            QWidget#TermPopup {
                border: 1px solid #78909C; 
                border-radius: 4px;
            }
        """)
        
        cursor = self.app.editor.textCursor()
        if self.app.editor._omap:
            cursor.setPosition(self.app.editor._omap.to_display(ann.start))
        rect = self.app.editor.cursorRect(cursor)
        pos = self.app.editor.viewport().mapToGlobal(rect.topLeft())
        
        popup.adjustSize()
        pos.setY(pos.y() - popup.height() - 5)
        popup.move(pos)
        
        original_hide = popup.hideEvent
        def on_hide(e):
            self.app.editor.clear_explanation_highlight()
            self.app._refresh_status()
            if original_hide:
                original_hide(e)
        popup.hideEvent = on_hide
        
        popup.show()
        return True

    def add_context_menu_actions(self, menu: QMenu, ann: Optional[Annotation], sel_start: int, sel_end: int):
        if ann is not None:
            menu.addSeparator()
            act_edit = QAction("編輯概念", menu)
            act_edit.triggered.connect(lambda: self._edit_concept(ann))
            menu.addAction(act_edit)
            
            act_reselect = QAction("重新選取解釋", menu)
            act_reselect.triggered.connect(lambda: self._reselect_explanation(ann))
            menu.addAction(act_reselect)
            menu.addSeparator()

    def _edit_concept(self, ann: Annotation):
        s_term, e_term = ann.start, ann.end
        s_exp, e_exp = getattr(ann, "explanation_start", None), getattr(ann, "explanation_end", None)
        term_text = self.app.doc.text[s_term:e_term]
        exp_text = self.app.doc.text[s_exp:e_exp] if s_exp is not None and e_exp is not None else "(無)"
        
        dlg = TermConceptDialog(self.app.doc.concepts, term_text, exp_text, 
                                default_bound_id=getattr(ann, "concept_id", None), 
                                default_broader_id=getattr(ann, "broader_concept_id", None), 
                                parent=self.app, is_edit_mode=True)
                                
        if dlg.exec():
            b_id, b_name, br_id, br_name, wants_back = dlg.get_results()
            if wants_back:
                # Trigger reselect instead
                self._reselect_explanation(ann)
                return
            
            concept_id = None
            if b_name:
                existing_id = next((cid for cid, name in self.app.doc.concepts.items() if name == b_name), None)
                if existing_id:
                    concept_id = existing_id
                else:
                    concept_id = "C_" + uuid.uuid4().hex[:8]
                    self.app.doc.concepts[concept_id] = b_name
            elif b_id:
                concept_id = b_id
                
            broader_id = None
            if br_name:
                existing_id = next((cid for cid, name in self.app.doc.concepts.items() if name == br_name), None)
                if existing_id:
                    broader_id = existing_id
                else:
                    broader_id = "C_" + uuid.uuid4().hex[:8]
                    self.app.doc.concepts[broader_id] = br_name
            elif br_id:
                broader_id = br_id
                
            ann.concept_id = concept_id
            ann.broader_concept_id = broader_id
            self.app.doc.dirty = True
            self.app.concept_panel.refresh(self.app.doc)
            self.app._refresh_status()

    def _reselect_explanation(self, ann: Annotation):
        old_s_exp = getattr(ann, "explanation_start", None)
        old_e_exp = getattr(ann, "explanation_end", None)
        
        # Enter pending state with just the annotation ID
        self.app._pending_term_info = ("reselect", ann.id)
        
        term_color = QColor("#FFF59D")
        group_id = list(ann.labels.keys())[0] if ann.labels else None
        label_id = ann.labels[group_id] if group_id else None
        if group_id and label_id:
            g = self.app.mode.group(group_id)
            if g:
                l = g.label(label_id)
                if l and l.color:
                    c = QColor(l.color)
                    c.setAlpha(120)
                    term_color = c
                    
        self.app.editor.highlight_pending_term(ann.start, ann.end, term_color)
        
        if old_s_exp is not None and old_e_exp is not None:
            base_exp_c_str = self.app.prefs.ui.get("explanation_highlight_color", "#90CAF9")
            exp_c = QColor(base_exp_c_str)
            exp_c.setAlpha(120)
            self.app.editor.highlight_explanation(old_s_exp, old_e_exp, exp_c)
            
        self.app._show_hud()
        self.app.status.showMessage("重新選取解釋段落 (按 Esc 取消)", 0)
        self.app.editor.refresh_highlights()


    def suppress_default_context_menu(self, ann) -> bool:
        return ann is not None
