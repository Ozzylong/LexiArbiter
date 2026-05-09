"""PyInstaller helper - bundles LexiArbiter into a Windows .exe.

Usage (from project root, in your venv):

    pip install pyinstaller
    python build_exe.py

The output exe lands in `dist/LexiArbiter.exe`. The `configs/` folder is
copied next to the exe so users can edit annotation modes / preferences
without rebuilding.
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

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "LexiArbiter",
        "--noconfirm",
        "--clean",
        "--windowed",         # no console window on Windows
        "--onefile",
        str(HERE / "main.py"),
    ]
    print("執行：", " ".join(cmd))
    subprocess.check_call(cmd, cwd=HERE)

    # Copy configs next to the resulting exe so they stay user-editable.
    target_dir = DIST
    src_configs = HERE / "configs"
    dst_configs = target_dir / "configs"
    if dst_configs.exists():
        shutil.rmtree(dst_configs)
    shutil.copytree(src_configs, dst_configs)
    print(f"已將 configs/ 複製到 {dst_configs}")
    print(f"\n打包完成：{target_dir / 'LexiArbiter.exe'}")
    print("請保留 LexiArbiter.exe 與旁邊的 configs/ 在同一個資料夾即可。")


if __name__ == "__main__":
    main()
