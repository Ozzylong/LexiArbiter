"""Base mode handler interface."""
from typing import Optional
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMenu
from ..core.models import Annotation

class BaseModeHandler:
    """Base class for all annotation mode handlers."""
    
    def __init__(self, app):
        """
        :param app: The main ApplicationWindow (MainWindow) instance.
        """
        self.app = app

    def add_context_menu_actions(self, menu: QMenu, ann: Optional[Annotation], sel_start: int, sel_end: int):
        """
        Override this to add mode-specific actions to the context menu.
        """
        pass

    def on_annotation_clicked(self, ann_id: str) -> bool:
        """
        Override this to handle clicks on annotations.
        Return True if the click was fully handled and no default action is needed.
        """
        return False
        
    def handle_selection_finished(self, global_pos: QPoint) -> bool:
        """
        Override this to handle selection finished events (like popping up a custom dialog).
        Return True if handled.
        """
        return False

    def handle_apply_label(self, group_id: str, label_id: str) -> bool:
        """
        Override this to intercept apply label events.
        Return True if handled completely.
        """
        return False


    def suppress_default_context_menu(self, ann) -> bool:
        return False
