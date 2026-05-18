"""PyInstaller helper - bundles LexiArbiter into a Windows distribution folder.

Usage (from project root, in your venv):

    pip install pyinstaller
    python build_exe.py

The output is a `dist/LexiArbiter/` folder containing `LexiArbiter.exe`
(with embedded icon), PyInstaller's `_internal/` dependency dir, plus
`configs/` and `assets/` copied next to the exe so users can edit
annotation modes / preferences without rebuilding.

We deliberately use onedir (folder) mode rather than --onefile because
single-file PyInstaller executables self-extract to %TEMP% on launch,
which Windows Defender / SmartScreen heuristics often flag as suspicious.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
BUILD = HERE / "build"


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("找不到 PyInstaller，請先 `pip install pyinstaller` 後再執行。",
              file=sys.stderr)
        sys.exit(1)

    icon_path = HERE / "assets" / "LexiArbiter_icon.ico"
    if not icon_path.exists():
        print(f"找不到 icon 檔：{icon_path}，將以 PyInstaller 預設 icon 打包。",
              file=sys.stderr)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "LexiArbiter",
        "--noconfirm",
        "--clean",
        "--windowed",         # no console window on Windows
        str(HERE / "main.py"),
    ]
    if icon_path.exists():
        # 插在 main.py 之前，--icon 嵌進 exe 的 PE 資源（影響檔案總管縮圖）
        cmd[-1:-1] = ["--icon", str(icon_path)]
    print("執行：", " ".join(cmd))
    subprocess.check_call(cmd, cwd=HERE)

    # onedir 模式下 PyInstaller 會把成品放在 dist/<name>/，所以 configs 與
    # assets 要複製到那個資料夾內部、與 exe 同層，app_root() 才找得到。
    target_dir = DIST / "LexiArbiter"

    def _sync_tree(src: Path, dst: Path, label: str) -> None:
        if not src.exists():
            print(f"找不到來源資料夾：{src}，略過 {label} 複製。", file=sys.stderr)
            return
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"已將 {label} 複製到 {dst}")

    _sync_tree(HERE / "configs", target_dir / "configs", "configs/")
    _sync_tree(HERE / "assets", target_dir / "assets", "assets/")

    print(f"\n打包完成：{target_dir / 'LexiArbiter.exe'}")
    print("請保留整個 LexiArbiter 資料夾（含 exe、_internal/、configs/、assets/）一起分發。")


if __name__ == "__main__":
    main()
