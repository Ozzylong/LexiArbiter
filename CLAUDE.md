# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

LexiArbiter is a PySide6 desktop GUI for annotating Taiwanese judicial judgments to produce multi-task-learning (MTL) training data. It reads judicial open-data JSON (extracts the `JFULL` field), lets users highlight character spans with multiple labels at once, exports model-ready `.txt` (`<P>tag1,tag2|text</P>`) and saves in-progress work as `.lexa`. This is a manual annotation tool — no LLM/API calls, no database, no network. PySide6 is the only runtime dependency.

The README and most UI strings, log messages, and code comments are in Traditional Chinese — preserve the Chinese strings when editing, they are user-facing.

## Critical Rules that MUST follow
- Use Traditional Chinese(TW) to interact with user (include but not limited to answer user's question, providing commit message)
- After the code is modified, provide commit message to user
- DO NOT add any program function or code that user are not permitted
- If there is some change of the program function/code, remember to clean up the zombie code that are no longer needed, if you are not sure about it, ask user how to handle it.

## Common commands

Run from source (Windows / PowerShell):

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Build a standalone Windows executable:

```
pip install pyinstaller
python build_exe.py
```

The output is `dist/LexiArbiter.exe` plus a sibling `dist/configs/` directory. The two must stay together — `build_exe.py` deliberately copies `configs/` next to the exe so users can edit annotation modes without rebuilding.

Python 3.10+ is required; the README recommends 3.11.

No test, lint, or CI infrastructure exists (no `pyproject.toml`, no `Makefile`, no `.github/workflows`, no test files). Do not fabricate test commands. If adding tests, pytest + pytest-qt is the natural choice.

## Architecture

Layering inside `lexiarbiter/`:

- `core/` — pure logic, no Qt imports.
  - `models.py` — `Annotation`, `Document` dataclasses.
  - `io.py` — load/save `.json` / `.lexa` / `.txt` (`load_any`, `load_judicial_json`, `load_lexa`, `save_lexa`, `export_txt`).
  - `config.py` — `AnnotationMode`, `GroupDef`, `LabelDef`, `UserPreferences`, plus `app_root()`.
  - `logger.py` — logging setup and `install_exception_hook`.
- `widgets/` — Qt UI.
  - `editor.py` — `AnnotationEditor` (read-only `QTextEdit` subclass that renders highlights) and the `_OffsetMap` helper.
  - `file_panel.py` — sibling-files browser.
- `app.py` — `MainWindow` orchestrates everything (~700 lines: menus, shortcuts, mode switching, file open/save/export, overlap-resolution UX).
- `main.py` — entry point. Sets up logging, installs `sys.excepthook` → `MainWindow.emergency_save`, then runs `QApplication`.

Configs live in `configs/` as hand-editable JSON (not Python):

- `annotation_modes/*.json` — schema definitions (groups, labels, colors, shortcuts, export format). Default: `legal_mtl.json` with groups 論證類別 (primary: 心證其他 / 大前提 / 小前提 / 結論) and 人稱 (auxiliary: 第一人稱 / 非第一人稱).
- `user_preferences.json` — per-user overrides (active mode, font, shortcut overrides). Kept separate from mode files so sharing modes can't clobber personal shortcuts.

Central data flow for a single file annotation cycle:

1. `MainWindow.action_open()` → `io.load_any(path)` dispatches by extension to `load_judicial_json` (extracts `JFULL`) or `load_lexa` (deserializes prior progress).
2. `AnnotationEditor.attach(doc, mode, prefs)` normalizes `\r\n` → `\n` for Qt display, builds an `_OffsetMap`, paints highlights.
3. User selects text → `MainWindow.apply_label(group_id, label_id)` builds/updates an `Annotation` (12-char UUID, `start` / `end` / `labels{group_id: label_id}`), handles overlap (prompts user to delete overlappers), marks `Document.dirty`, refreshes highlights.
4. Save with `io.save_lexa` (JSON with full text + annotations) or export with `io.export_txt` (formats per `mode.export` config: wrapper, separators, tag order).

## Non-obvious things to know

- **Storage-vs-display offset duality.** Annotation `start` / `end` are always offsets into the *original* text with `\r\n` line endings, but Qt displays normalized `\n`. Code that reads cursor positions from the widget must convert through `_OffsetMap` (`lexiarbiter/widgets/editor.py`) before touching `Annotation`. Don't "fix" the offsets to match Qt — the persistence format depends on storage offsets.
- **`configs/` resolution differs between source and frozen exe.** See `app_root()` in `lexiarbiter/core/config.py`. From source it's the project root; from the PyInstaller exe it's `Path(sys.executable).parent`. If you change config-loading, test both paths.
- **`schema_id` round-trip.** `.lexa` files embed the mode `id` they were saved under. Loading a `.lexa` whose `schema_id` differs from the active mode prompts the user to switch — that's intentional, not a bug.
- **Crash safety.** `install_exception_hook(win.emergency_save)` in `main.py` writes a `.crash_backup.lexa` next to the active file on uncaught exceptions. Don't remove the hook when refactoring `main.py`.
- **Three file extensions, three roles** — keep them straight:
  - `.json` — upstream judicial open-data input (read-only from our perspective).
  - `.lexa` — our progress format (JSON internally; full text + annotations for relay annotation between users).
  - `.txt` — model-ready export, one `<P>tag1,tag2|text</P>` per paragraph.
- **No tests exist.** When adding logic, the natural seams to unit-test are `core/io.py` (round-trip serialization, export formatting) and `core/models.py` (offset math, overlap detection). UI is GUI-tested manually.
