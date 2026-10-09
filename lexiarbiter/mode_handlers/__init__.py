from .base_handler import BaseModeHandler
from .term_definition_handler import TermDefinitionHandler

def get_handler(mode_id: str, app) -> BaseModeHandler:
    if mode_id == "term_definition":
        return TermDefinitionHandler(app)
    return BaseModeHandler(app)
